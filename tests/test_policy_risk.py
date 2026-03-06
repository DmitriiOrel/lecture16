from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from delta_bot.config import load_config
from delta_bot.execution import ExecutionPlanner
from delta_bot.policy import compute_target_positions_from_basis_zscore
from delta_bot.reward import RewardInputs, compute_reward
from delta_bot.risk import RiskContext, RiskEngine


class BotCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = load_config(ROOT / "config" / "micro_near_v1.json")

    def test_policy_respects_min_funds(self) -> None:
        out = compute_target_positions_from_basis_zscore(
            basis_z=2.5,
            spot_price=100.0,
            current_spot_qty=0.0,
            current_futures_contracts=0,
            policy_cfg=self.cfg.policy,
            instr_cfg=self.cfg.instruments,
            delta_cfg=self.cfg.delta_neutral,
        )
        self.assertEqual(out.target_spot_qty, 0.0)
        self.assertEqual(out.target_futures_contracts, 0)

    def test_policy_basis_entry_generates_hedged_position(self) -> None:
        out = compute_target_positions_from_basis_zscore(
            basis_z=2.0,
            spot_price=1.3,
            current_spot_qty=0.0,
            current_futures_contracts=0,
            policy_cfg=self.cfg.policy,
            instr_cfg=self.cfg.instruments,
            delta_cfg=self.cfg.delta_neutral,
        )
        self.assertGreater(out.target_spot_qty, 0.0)
        # Hedge ratio is -1.0, so contracts should be < 0.
        self.assertAlmostEqual(out.z_score, 2.0, places=8)
        self.assertLessEqual(out.target_futures_contracts, 0)
        self.assertLess(abs(out.target_net_delta_base), 0.11)

    def test_policy_basis_exit_closes_pair(self) -> None:
        out = compute_target_positions_from_basis_zscore(
            basis_z=0.05,
            spot_price=1.3,
            current_spot_qty=0.5,
            current_futures_contracts=-5,
            policy_cfg=self.cfg.policy,
            instr_cfg=self.cfg.instruments,
            delta_cfg=self.cfg.delta_neutral,
        )
        self.assertEqual(out.target_spot_qty, 0.0)
        self.assertEqual(out.target_futures_contracts, 0)

    def test_reward_formula(self) -> None:
        r = compute_reward(
            RewardInputs(
                pnl_usdt=0.12,
                fee_usdt=0.01,
                funding_usdt=0.0,
                net_delta_notional_usdt=0.2,
                delta_contracts=2,
                drawdown_fraction=0.02,
            ),
            self.cfg.reward,
        )
        self.assertIsInstance(r, float)
        self.assertLess(r, 0.12)  # penalties reduce raw pnl

    def test_risk_block_on_gross_notional(self) -> None:
        engine = RiskEngine(self.cfg.risk_limits)
        ctx = RiskContext(
            equity_usdt=15.0,
            peak_equity_usdt=15.0,
            daily_pnl_usdt=0.0,
            current_spot_qty=0.0,
            current_futures_contracts=0,
            spot_price=1.3,
            futures_price=1.3,
            futures_multiplier_base=0.1,
            api_error_streak=0,
            expected_slippage_bps=2.0,
        )
        dec = engine.evaluate(
            ctx=ctx,
            target_spot_qty=10.0,  # 13 USDT spot notional alone
            target_futures_contracts=0,
            is_new_entry=True,
        )
        self.assertFalse(dec.allowed)
        self.assertIn("Gross notional", dec.reason)

    def test_execution_planner_chunks_orders(self) -> None:
        planner = ExecutionPlanner(self.cfg.instruments, self.cfg.risk_limits, self.cfg.execution)
        orders = planner.plan_rebalance(
            current_spot_qty=0.0,
            current_futures_contracts=0,
            target_spot_qty=0.9,  # > max single notional at 1.3 price
            target_futures_contracts=-9,
            spot_price=1.3,
            futures_price=1.3,
        )
        self.assertGreater(len(orders), 2)
        spot_orders = [o for o in orders if o.venue == "spot"]
        self.assertGreater(len(spot_orders), 1)

    def test_execution_planner_two_buy_orders_per_venue(self) -> None:
        planner = ExecutionPlanner(self.cfg.instruments, self.cfg.risk_limits, self.cfg.execution)
        orders = planner.plan_rebalance(
            current_spot_qty=0.0,
            current_futures_contracts=0,
            target_spot_qty=0.4,
            target_futures_contracts=4,
            spot_price=1.3,
            futures_price=1.3,
        )
        spot_buys = [o for o in orders if o.venue == "spot" and o.side == "buy"]
        fut_buys = [o for o in orders if o.venue == "futures" and o.side == "buy"]
        self.assertEqual(len(spot_buys), 2)
        self.assertEqual(len(fut_buys), 2)

    def test_execution_planner_two_sell_orders_per_venue(self) -> None:
        planner = ExecutionPlanner(self.cfg.instruments, self.cfg.risk_limits, self.cfg.execution)
        orders = planner.plan_rebalance(
            current_spot_qty=0.0,
            current_futures_contracts=0,
            target_spot_qty=-0.4,
            target_futures_contracts=-4,
            spot_price=1.3,
            futures_price=1.3,
        )
        spot_sells = [o for o in orders if o.venue == "spot" and o.side == "sell"]
        fut_sells = [o for o in orders if o.venue == "futures" and o.side == "sell"]
        self.assertEqual(len(spot_sells), 2)
        self.assertEqual(len(fut_sells), 2)

    def test_execution_planner_skips_spot_remainder_below_exchange_min_size(self) -> None:
        planner = ExecutionPlanner(self.cfg.instruments, self.cfg.risk_limits, self.cfg.execution)
        # Delta below 0.1 NEAR should be skipped to avoid KuCoin 400100 min-size rejection.
        orders = planner.plan_rebalance(
            current_spot_qty=0.0,
            current_futures_contracts=0,
            target_spot_qty=0.0999,
            target_futures_contracts=0,
            spot_price=1.26,
            futures_price=1.26,
        )
        spot_orders = [o for o in orders if o.venue == "spot"]
        self.assertEqual(len(spot_orders), 0)

    def test_execution_planner_handles_float_boundary_near_min_size(self) -> None:
        planner = ExecutionPlanner(self.cfg.instruments, self.cfg.risk_limits, self.cfg.execution)
        # Float artifacts like 0.099999999 should still produce a 0.1 lot order.
        orders = planner.plan_rebalance(
            current_spot_qty=0.0,
            current_futures_contracts=0,
            target_spot_qty=0.099999999,
            target_futures_contracts=0,
            spot_price=1.26,
            futures_price=1.26,
        )
        spot_orders = [o for o in orders if o.venue == "spot"]
        self.assertEqual(len(spot_orders), 1)
        self.assertAlmostEqual(spot_orders[0].size, 0.1, places=8)


if __name__ == "__main__":
    unittest.main()
