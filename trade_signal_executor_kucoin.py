from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from delta_bot.config import BotConfig, load_config
from delta_bot.execution import ExecutionPlanner, PlannedOrder
from delta_bot.kucoin_client import KuCoinApiError, KuCoinRestClient
from delta_bot.policy import TargetPositions, compute_target_positions
from delta_bot.risk import RiskContext, RiskEngine
from delta_bot.state_store import JsonStateStore, RuntimeState

DEFAULT_OUTPUT_DIR = Path("reports/kucoin_rl")
MANUAL_FORCE_ACTIONS = {
    "BUY_BOTH",
    "SELL_BOTH",
    "BUY_SPOT",
    "SELL_SPOT",
    "BUY_FUTURES",
    "SELL_FUTURES",
}


def configure_console_utf8() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Исполнитель KuCoin state->orders: читает последний JSON состояния из ноутбука "
            "и выполняет ребалансировку (dry-run/live) с опцией принудительного BUY/SELL."
        )
    )
    parser.add_argument(
        "--state-json",
        default="",
        help="Путь к JSON состояния (latest_forecast_signal_*.json).",
    )
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "micro_near_v1_1m.json"),
        help="Путь к конфигурации бота.",
    )
    parser.add_argument(
        "--mode",
        choices=["shadow", "live"],
        default="shadow",
        help="shadow: без отправки ордеров, live: реальная отправка.",
    )
    parser.add_argument(
        "--expected-slippage-bps",
        type=float,
        default=3.0,
        help="Ожидаемое проскальзывание для risk engine.",
    )
    parser.add_argument(
        "--force-action",
        choices=[
            "",
            "BUY",
            "SELL",
            "HOLD",
            "BUY_BOTH",
            "SELL_BOTH",
            "BUY_SPOT",
            "SELL_SPOT",
            "BUY_FUTURES",
            "SELL_FUTURES",
        ],
        default="",
        help="Принудительное действие для интеграционного теста.",
    )
    parser.add_argument(
        "--spot-qty",
        type=float,
        default=0.1,
        help="Размер spot-ордера в базовой валюте для ручных force-режимов.",
    )
    parser.add_argument(
        "--futures-contracts",
        type=int,
        default=1,
        help="Размер futures-ордера в контрактах для ручных force-режимов.",
    )
    parser.add_argument(
        "--allow-short",
        action="store_true",
        default=False,
        help=(
            "Разрешить расчет short-цели в policy. "
            "Внимание: spot short без margin borrowing не поддерживается."
        ),
    )
    parser.add_argument(
        "--state-file",
        default=str(ROOT / ".runtime" / "trade_signal_state.json"),
        help="Файл runtime-state (daily pnl, peak equity, api-error streak).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Папка для strategy state/log JSON.",
    )
    parser.add_argument(
        "--run-real-order",
        action="store_true",
        default=False,
        help="Явно разрешить отправку реальных ордеров (вместо shadow).",
    )
    return parser.parse_args()


def _base_currency(spot_symbol: str) -> str:
    return spot_symbol.split("-")[0]


def _read_state_payload(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"State JSON not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def _extract_signal_from_payload(payload: dict) -> tuple[float, float]:
    ret_hat = float(payload.get("ret_hat", 0.0))
    sigma_hat = float(payload.get("sigma_hat", 0.0))
    if not math.isfinite(ret_hat):
        ret_hat = 0.0
    if (not math.isfinite(sigma_hat)) or sigma_hat <= 0:
        sigma_hat = 0.003
    return ret_hat, sigma_hat


def _extract_prices(payload: dict, client: KuCoinRestClient, cfg: BotConfig) -> tuple[float, float]:
    spot_price = float(payload.get("spot_price", 0.0) or 0.0)
    futures_price = float(payload.get("futures_price", 0.0) or 0.0)
    if spot_price > 0 and futures_price > 0:
        return spot_price, futures_price
    spot_t = client.get_spot_ticker(cfg.instruments.spot_symbol)
    fut_t = client.get_futures_ticker(cfg.instruments.futures_symbol)
    return float(spot_t["price"]), float(fut_t["price"])


def _current_positions(client: KuCoinRestClient, cfg: BotConfig) -> tuple[float, int]:
    if not client.has_auth:
        return 0.0, 0
    base_ccy = _base_currency(cfg.instruments.spot_symbol)
    spot_qty = client.get_spot_account_balance(base_ccy, account_type="trade")
    fut_contracts = client.get_futures_position_contracts(cfg.instruments.futures_symbol)
    return spot_qty, fut_contracts


def _estimate_equity_usdt(
    client: KuCoinRestClient,
    cfg: BotConfig,
    spot_price: float,
    fallback_equity: float,
) -> float:
    if not client.has_auth:
        return fallback_equity
    base_ccy = _base_currency(cfg.instruments.spot_symbol)
    try:
        spot_usdt = client.get_spot_account_balance("USDT", account_type="trade")
        spot_base = client.get_spot_account_balance(base_ccy, account_type="trade")
        fut_equity = client.get_futures_account_equity("USDT")
        return spot_usdt + spot_base * spot_price + fut_equity
    except KuCoinApiError:
        return fallback_equity


def _forced_target(
    action: str,
    ret_hat: float,
    sigma_hat: float,
    spot_price: float,
    cfg: BotConfig,
    allow_short: bool,
) -> TargetPositions:
    policy_cfg = replace(cfg.policy, allow_spot_short=bool(allow_short))
    if action == "HOLD":
        return TargetPositions(
            z_score=0.0,
            target_spot_notional_usdt=0.0,
            target_spot_qty=0.0,
            target_futures_contracts=0,
            target_futures_base_qty=0.0,
            target_net_delta_base=0.0,
        )
    if action == "BUY":
        ret_hat = abs(sigma_hat)
    elif action == "SELL":
        ret_hat = -abs(sigma_hat)
    return compute_target_positions(
        ret_hat=ret_hat,
        sigma_hat=sigma_hat,
        spot_price=spot_price,
        policy_cfg=policy_cfg,
        instr_cfg=cfg.instruments,
    )


def _manual_action_deltas(
    action: str,
    spot_qty: float,
    futures_contracts: int,
) -> tuple[float, int]:
    s_qty = abs(float(spot_qty))
    f_qty = abs(int(futures_contracts))
    mapping: Dict[str, tuple[float, int]] = {
        "BUY_BOTH": (s_qty, f_qty),
        "SELL_BOTH": (-s_qty, -f_qty),
        "BUY_SPOT": (s_qty, 0),
        "SELL_SPOT": (-s_qty, 0),
        "BUY_FUTURES": (0.0, f_qty),
        "SELL_FUTURES": (0.0, -f_qty),
    }
    if action not in mapping:
        raise ValueError(f"Unsupported manual force action: {action}")
    return mapping[action]


def _manual_orders_from_deltas(
    *,
    cfg: BotConfig,
    spot_delta: float,
    futures_delta_contracts: int,
) -> List[PlannedOrder]:
    orders: List[PlannedOrder] = []
    if abs(spot_delta) > 1e-12:
        orders.append(
            PlannedOrder(
                venue="spot",
                symbol=cfg.instruments.spot_symbol,
                side="buy" if spot_delta > 0 else "sell",
                size=abs(spot_delta),
                order_type=cfg.execution.order_type,
            )
        )
    if futures_delta_contracts != 0:
        orders.append(
            PlannedOrder(
                venue="futures",
                symbol=cfg.instruments.futures_symbol,
                side="buy" if futures_delta_contracts > 0 else "sell",
                size=float(abs(futures_delta_contracts)),
                order_type=cfg.execution.order_type,
            )
        )
    return orders


def _execute_orders(
    client: KuCoinRestClient,
    orders: List[PlannedOrder],
    max_retries: int,
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for order in orders:
        retries = max(max_retries, 1)
        for attempt in range(1, retries + 1):
            try:
                if order.venue == "spot":
                    resp = client.place_spot_market_order(
                        symbol=order.symbol,
                        side=order.side,
                        size=order.size,
                    )
                elif order.venue == "futures":
                    resp = client.place_futures_market_order(
                        symbol=order.symbol,
                        side=order.side,
                        contracts=int(order.size),
                        leverage="1",
                        margin_mode="CROSS",
                    )
                else:
                    raise KuCoinApiError(f"Unknown venue: {order.venue}")
                out.append(
                    {
                        "venue": order.venue,
                        "symbol": order.symbol,
                        "side": order.side,
                        "size": str(order.size),
                        "orderId": str(resp.get("orderId", "")),
                        "attempts": str(attempt),
                    }
                )
                break
            except Exception as exc:  # noqa: BLE001
                if attempt >= retries:
                    raise KuCoinApiError(
                        f"Order failed after {retries} attempts: {order.venue} {order.side} "
                        f"{order.symbol} size={order.size}. Error: {exc}"
                    ) from exc
                time.sleep(0.25 * attempt)
    return out


def _precheck_spot_inventory(current_spot_qty: float, planned_orders: List[PlannedOrder]) -> None:
    needed_spot_sell = sum(
        max(order.size, 0.0)
        for order in planned_orders
        if order.venue == "spot" and order.side == "sell"
    )
    if needed_spot_sell <= current_spot_qty + 1e-12:
        return
    raise KuCoinApiError(
        "Insufficient spot base inventory for planned spot sells. "
        f"Have={current_spot_qty}, need={needed_spot_sell}. "
        "Spot short selling is not supported by this executor without margin borrowing."
    )


def _find_latest_json() -> Path | None:
    roots = [ROOT / "reports", Path.home() / "Downloads", Path.home() / "Загрузки"]
    found: list[Path] = []
    for base in roots:
        if not base.exists():
            continue
        try:
            found.extend(base.rglob("latest_forecast_signal_*.json"))
        except Exception:
            continue
    if not found:
        return None
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0]


def main() -> int:
    configure_console_utf8()
    args = parse_args()

    cfg = load_config(args.config)
    client = KuCoinRestClient.from_env()
    mode = "live" if args.run_real_order else args.mode

    state_json_path: Path
    if args.state_json:
        state_json_path = Path(args.state_json).expanduser().resolve()
    else:
        auto = _find_latest_json()
        if auto is None:
            raise FileNotFoundError(
                "State JSON not found. Pass --state-json or export latest_forecast_signal_*.json first."
            )
        state_json_path = auto
    payload = _read_state_payload(state_json_path)

    ret_hat, sigma_hat = _extract_signal_from_payload(payload)
    spot_price, futures_price = _extract_prices(payload, client=client, cfg=cfg)
    current_spot_qty, current_futures_contracts = _current_positions(client=client, cfg=cfg)
    equity_usdt = _estimate_equity_usdt(
        client=client,
        cfg=cfg,
        spot_price=spot_price,
        fallback_equity=cfg.account.equity_usdt,
    )

    state_store = JsonStateStore(args.state_file)
    runtime_state: RuntimeState = state_store.load(default_equity_usdt=cfg.account.equity_usdt)
    runtime_state.roll_day_if_needed(equity_usdt=equity_usdt)
    daily_pnl_usdt = equity_usdt - runtime_state.day_start_equity_usdt

    manual_force_mode = bool(args.force_action and args.force_action in MANUAL_FORCE_ACTIONS)
    if args.force_action and not manual_force_mode:
        target = _forced_target(
            action=args.force_action,
            ret_hat=ret_hat,
            sigma_hat=sigma_hat,
            spot_price=spot_price,
            cfg=cfg,
            allow_short=args.allow_short,
        )
        action_label = f"FORCED_{args.force_action}"
    elif manual_force_mode:
        spot_delta, futures_delta_contracts = _manual_action_deltas(
            action=args.force_action,
            spot_qty=args.spot_qty,
            futures_contracts=args.futures_contracts,
        )
        target = TargetPositions(
            z_score=0.0,
            target_spot_notional_usdt=(current_spot_qty + spot_delta) * spot_price,
            target_spot_qty=current_spot_qty + spot_delta,
            target_futures_contracts=current_futures_contracts + futures_delta_contracts,
            target_futures_base_qty=(current_futures_contracts + futures_delta_contracts)
            * cfg.instruments.futures_multiplier_base,
            target_net_delta_base=(current_spot_qty + spot_delta)
            + (current_futures_contracts + futures_delta_contracts)
            * cfg.instruments.futures_multiplier_base,
        )
        action_label = f"FORCED_{args.force_action}"
    else:
        policy_cfg = replace(cfg.policy, allow_spot_short=bool(args.allow_short))
        target = compute_target_positions(
            ret_hat=ret_hat,
            sigma_hat=sigma_hat,
            spot_price=spot_price,
            policy_cfg=policy_cfg,
            instr_cfg=cfg.instruments,
        )
        action_label = "POLICY"

    risk_engine = RiskEngine(cfg.risk_limits)
    risk_decision = risk_engine.evaluate(
        ctx=RiskContext(
            equity_usdt=equity_usdt,
            peak_equity_usdt=runtime_state.peak_equity_usdt,
            daily_pnl_usdt=daily_pnl_usdt,
            current_spot_qty=current_spot_qty,
            current_futures_contracts=current_futures_contracts,
            spot_price=spot_price,
            futures_price=futures_price,
            futures_multiplier_base=cfg.instruments.futures_multiplier_base,
            api_error_streak=runtime_state.api_error_streak,
            expected_slippage_bps=float(args.expected_slippage_bps),
        ),
        target_spot_qty=target.target_spot_qty,
        target_futures_contracts=target.target_futures_contracts,
        is_new_entry=(abs(current_spot_qty) < 1e-12 and current_futures_contracts == 0),
    )

    planned_orders: List[PlannedOrder] = []
    sent_orders: List[Dict[str, str]] = []
    blocked_reason = ""

    if risk_decision.allowed:
        if manual_force_mode:
            spot_delta, futures_delta_contracts = _manual_action_deltas(
                action=args.force_action,
                spot_qty=args.spot_qty,
                futures_contracts=args.futures_contracts,
            )
            planned_orders = _manual_orders_from_deltas(
                cfg=cfg,
                spot_delta=spot_delta,
                futures_delta_contracts=futures_delta_contracts,
            )
        else:
            planner = ExecutionPlanner(cfg.instruments, cfg.risk_limits, cfg.execution)
            planned_orders = planner.plan_rebalance(
                current_spot_qty=current_spot_qty,
                current_futures_contracts=current_futures_contracts,
                target_spot_qty=target.target_spot_qty,
                target_futures_contracts=target.target_futures_contracts,
                spot_price=spot_price,
                futures_price=futures_price,
            )
        try:
            _precheck_spot_inventory(current_spot_qty=current_spot_qty, planned_orders=planned_orders)
        except KuCoinApiError as exc:
            blocked_reason = str(exc)

    if mode == "live" and not client.has_auth:
        raise KuCoinApiError("Live mode requires KUCOIN_API_KEY/SECRET/PASSPHRASE in environment")

    try:
        if mode == "live" and risk_decision.allowed and not blocked_reason and planned_orders:
            sent_orders = _execute_orders(
                client=client,
                orders=planned_orders,
                max_retries=cfg.execution.max_retries,
            )
        runtime_state.api_error_streak = 0
    except Exception:  # noqa: BLE001
        runtime_state.api_error_streak += 1
        raise
    finally:
        runtime_state.roll_day_if_needed(equity_usdt=equity_usdt)
        state_store.save(runtime_state)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "mode": mode,
        "action_label": action_label,
        "state_json_path": str(state_json_path),
        "ret_hat": ret_hat,
        "sigma_hat": sigma_hat,
        "spot_price": spot_price,
        "futures_price": futures_price,
        "equity_usdt": equity_usdt,
        "current_spot_qty": current_spot_qty,
        "current_futures_contracts": current_futures_contracts,
        "target": asdict(target),
        "risk_allowed": risk_decision.allowed,
        "risk_reason": risk_decision.reason,
        "blocked_reason": blocked_reason,
        "planned_orders": [asdict(x) for x in planned_orders],
        "sent_orders": sent_orders,
    }
    state_out = output_dir / "strategy_state_kucoin.json"
    state_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("State JSON      :", state_json_path)
    print("Mode            :", mode)
    print("Action          :", action_label)
    print("Risk            :", risk_decision.allowed, "-", risk_decision.reason)
    if blocked_reason:
        print("Blocked         :", blocked_reason)
    print("Planned orders  :", len(planned_orders))
    print("Sent orders     :", len(sent_orders))
    print("Report saved    :", state_out.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
