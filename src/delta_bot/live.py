from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

from .config import BotConfig, load_config
from .execution import ExecutionPlanner, PlannedOrder
from .kucoin_client import KuCoinApiError, KuCoinRestClient
from .policy import (
    FLAT,
    TargetPositions,
    compute_target_positions_from_basis_zscore,
    infer_policy_regime,
)
from .risk import RiskContext, RiskDecision, RiskEngine
from .signal import (
    basis_zscore_signal_from_candles,
    futures_granularity_from_minutes,
    spot_candle_type_from_minutes,
)
from .state_store import JsonStateStore, RuntimeState


@dataclass
class RebalanceResult:
    mode: str
    equity_usdt: float
    signal_model: str
    basis: float
    basis_mean: float
    basis_std: float
    basis_z: float
    regime: str
    spot_price: float
    futures_price: float
    current_spot_qty: float
    current_futures_contracts: int
    target: TargetPositions
    risk: RiskDecision
    planned_orders: List[PlannedOrder]
    sent_orders: List[Dict[str, str]]


def _base_currency(spot_symbol: str) -> str:
    return spot_symbol.split("-")[0]


def _extract_prices(client: KuCoinRestClient, cfg: BotConfig) -> tuple[float, float]:
    spot_t = client.get_spot_ticker(cfg.instruments.spot_symbol)
    fut_t = client.get_futures_ticker(cfg.instruments.futures_symbol)
    return float(spot_t["price"]), float(fut_t["price"])


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


def _current_positions(
    client: KuCoinRestClient,
    cfg: BotConfig,
) -> tuple[float, int]:
    if not client.has_auth:
        return 0.0, 0
    base_ccy = _base_currency(cfg.instruments.spot_symbol)
    spot_qty = client.get_spot_account_balance(base_ccy, account_type="trade")
    fut_contracts = client.get_futures_position_contracts(cfg.instruments.futures_symbol)
    return spot_qty, fut_contracts


def _execute_live_orders(
    client: KuCoinRestClient,
    orders: List[PlannedOrder],
    max_retries: int,
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    # Execute in planner order: spot leg first, then futures leg.
    for order in orders:
        last_error: Exception | None = None
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
                    )
                else:
                    raise KuCoinApiError(f"Unknown venue: {order.venue}")
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= retries:
                    raise KuCoinApiError(
                        f"Order failed after {retries} attempts: {order.venue} {order.side} "
                        f"{order.symbol} size={order.size}. Error: {exc}"
                    ) from exc
                time.sleep(0.25 * attempt)

        out.append(
            {
                "venue": order.venue,
                "symbol": order.symbol,
                "side": order.side,
                "size": str(order.size),
                "orderId": str(resp.get("orderId", "")),
                "attempts": str(1 if last_error is None else attempt),
            }
        )
    return out


def _precheck_spot_inventory(
    *,
    current_spot_qty: float,
    planned_orders: List[PlannedOrder],
) -> None:
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
        "Spot short selling is not supported by this bot without margin borrowing."
    )


def _append_jsonl(path: Path, payload: Dict[str, str | int | float | dict | list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, default=str) + "\n")


def run_once(
    *,
    config_path: str | Path,
    mode: str,
    state_file: str | Path,
    expected_slippage_bps: float,
) -> RebalanceResult:
    cfg = load_config(config_path)
    if cfg.timing.rebalance_tf_minutes != cfg.timing.data_tf_minutes:
        raise ValueError(
            "timing.rebalance_tf_minutes must match timing.data_tf_minutes for this strategy"
        )
    client = KuCoinRestClient.from_env()

    state_store = JsonStateStore(state_file)
    runtime_state: RuntimeState = state_store.load(default_equity_usdt=cfg.account.equity_usdt)
    orders_log_path = Path(state_file).parent / "live_orders.jsonl"

    spot_candle_type = spot_candle_type_from_minutes(cfg.timing.data_tf_minutes)
    fut_granularity = futures_granularity_from_minutes(cfg.timing.data_tf_minutes)

    spot_candles = client.get_spot_candles(
        symbol=cfg.instruments.spot_symbol,
        candle_type=spot_candle_type,
    )
    futures_candles = client.get_futures_candles(
        symbol=cfg.instruments.futures_symbol,
        granularity=fut_granularity,
    )

    spot_price, futures_price = _extract_prices(client, cfg)
    current_spot_qty, current_futures_contracts = _current_positions(client, cfg)

    basis_signal = basis_zscore_signal_from_candles(
        spot_candles=spot_candles,
        futures_candles=futures_candles,
        spot_price=spot_price,
        futures_price=futures_price,
        window=cfg.delta_neutral.basis_window,
        epsilon=cfg.policy.epsilon,
    )
    regime = infer_policy_regime(
        current_spot_qty=current_spot_qty,
        current_futures_contracts=current_futures_contracts,
    ).regime

    equity_usdt = _estimate_equity_usdt(
        client=client,
        cfg=cfg,
        spot_price=spot_price,
        fallback_equity=cfg.account.equity_usdt,
    )
    runtime_state.roll_day_if_needed(equity_usdt=equity_usdt)
    daily_pnl_usdt = equity_usdt - runtime_state.day_start_equity_usdt

    target = compute_target_positions_from_basis_zscore(
        basis_z=basis_signal.basis_z,
        spot_price=spot_price,
        current_spot_qty=current_spot_qty,
        current_futures_contracts=current_futures_contracts,
        policy_cfg=cfg.policy,
        instr_cfg=cfg.instruments,
        delta_cfg=cfg.delta_neutral,
    )

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
            expected_slippage_bps=expected_slippage_bps,
        ),
        target_spot_qty=target.target_spot_qty,
        target_futures_contracts=target.target_futures_contracts,
        is_new_entry=(
            regime == FLAT
            and (abs(target.target_spot_qty) > 1e-12 or target.target_futures_contracts != 0)
        ),
    )

    planner = ExecutionPlanner(cfg.instruments, cfg.risk_limits, cfg.execution)
    planned_orders: List[PlannedOrder] = []
    sent_orders: List[Dict[str, str]] = []

    try:
        if risk_decision.allowed:
            planned_orders = planner.plan_rebalance(
                current_spot_qty=current_spot_qty,
                current_futures_contracts=current_futures_contracts,
                target_spot_qty=target.target_spot_qty,
                target_futures_contracts=target.target_futures_contracts,
                spot_price=spot_price,
                futures_price=futures_price,
            )

            if mode == "live":
                if not client.has_auth:
                    raise KuCoinApiError("Live mode requires API credentials in env vars")
                _precheck_spot_inventory(
                    current_spot_qty=current_spot_qty,
                    planned_orders=planned_orders,
                )
                sent_orders = _execute_live_orders(
                    client=client,
                    orders=planned_orders,
                    max_retries=cfg.execution.max_retries,
                )
            runtime_state.api_error_streak = 0
    except Exception:  # noqa: BLE001
        runtime_state.api_error_streak += 1
        raise
    finally:
        if mode == "live" and sent_orders:
            _append_jsonl(
                orders_log_path,
                {
                    "spot_price": spot_price,
                    "futures_price": futures_price,
                    "planned_orders": [asdict(x) for x in planned_orders],
                    "sent_orders": sent_orders,
                    "equity_usdt": equity_usdt,
                    "signal_model": "basis_zscore",
                    "basis": basis_signal.basis,
                    "basis_mean": basis_signal.basis_mean,
                    "basis_std": basis_signal.basis_std,
                    "basis_z": basis_signal.basis_z,
                    "regime": regime,
                },
            )
        runtime_state.roll_day_if_needed(equity_usdt=equity_usdt)
        state_store.save(runtime_state)

    return RebalanceResult(
        mode=mode,
        equity_usdt=equity_usdt,
        signal_model="basis_zscore",
        basis=basis_signal.basis,
        basis_mean=basis_signal.basis_mean,
        basis_std=basis_signal.basis_std,
        basis_z=basis_signal.basis_z,
        regime=regime,
        spot_price=spot_price,
        futures_price=futures_price,
        current_spot_qty=current_spot_qty,
        current_futures_contracts=current_futures_contracts,
        target=target,
        risk=risk_decision,
        planned_orders=planned_orders,
        sent_orders=sent_orders,
    )


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "micro_near_v1.json"


def _default_state_file() -> Path:
    return Path(__file__).resolve().parents[2] / ".runtime" / "bot_state.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run micro delta-neutral KuCoin bot")
    parser.add_argument("--config", default=str(_default_config_path()))
    parser.add_argument("--state-file", default=str(_default_state_file()))
    parser.add_argument("--mode", choices=["shadow", "live"], default="shadow")
    parser.add_argument("--expected-slippage-bps", type=float, default=3.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument(
        "--sleep-seconds",
        type=int,
        default=0,
        help="Loop sleep in seconds. If 0, uses timing.rebalance_tf_minutes from config.",
    )
    args = parser.parse_args()
    cfg = load_config(args.config)
    sleep_seconds = (
        args.sleep_seconds
        if args.sleep_seconds > 0
        else max(int(cfg.timing.rebalance_tf_minutes * 60), 1)
    )

    def _run() -> None:
        result = run_once(
            config_path=args.config,
            mode=args.mode,
            state_file=args.state_file,
            expected_slippage_bps=args.expected_slippage_bps,
        )
        payload = asdict(result)
        print(json.dumps(payload, indent=2, default=str))

    if not args.loop:
        _run()
        return

    while True:
        try:
            _run()
        except Exception as exc:  # noqa: BLE001
            print(f"run_once error: {exc}")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
