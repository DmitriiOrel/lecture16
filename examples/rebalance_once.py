from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from delta_bot.config import load_config
from delta_bot.execution import ExecutionPlanner
from delta_bot.policy import compute_target_positions
from delta_bot.risk import RiskContext, RiskEngine


def main() -> None:
    cfg = load_config(ROOT / "config" / "micro_near_v1.json")

    # Example snapshot from market/model.
    spot_price = 1.31
    futures_price = 1.312
    ret_hat = 0.0025
    sigma_hat = 0.0075
    current_spot_qty = 0.0
    current_fut_contracts = 0

    target = compute_target_positions(
        ret_hat=ret_hat,
        sigma_hat=sigma_hat,
        spot_price=spot_price,
        policy_cfg=cfg.policy,
        instr_cfg=cfg.instruments,
    )

    risk = RiskEngine(cfg.risk_limits)
    decision = risk.evaluate(
        ctx=RiskContext(
            equity_usdt=15.0,
            peak_equity_usdt=15.0,
            daily_pnl_usdt=0.0,
            current_spot_qty=current_spot_qty,
            current_futures_contracts=current_fut_contracts,
            spot_price=spot_price,
            futures_price=futures_price,
            futures_multiplier_base=cfg.instruments.futures_multiplier_base,
            api_error_streak=0,
            expected_slippage_bps=3.0,
        ),
        target_spot_qty=target.target_spot_qty,
        target_futures_contracts=target.target_futures_contracts,
        is_new_entry=True,
    )

    print("risk_decision:", decision)
    print("target:", target)
    if not decision.allowed:
        return

    planner = ExecutionPlanner(cfg.instruments, cfg.risk_limits, cfg.execution)
    orders = planner.plan_rebalance(
        current_spot_qty=current_spot_qty,
        current_futures_contracts=current_fut_contracts,
        target_spot_qty=target.target_spot_qty,
        target_futures_contracts=target.target_futures_contracts,
        spot_price=spot_price,
        futures_price=futures_price,
    )
    print("planned_orders:")
    for order in orders:
        print(order)


if __name__ == "__main__":
    main()
