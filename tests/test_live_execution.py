from __future__ import annotations

import json
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from delta_bot.kucoin_client import KuCoinApiError
from delta_bot.live import run_once
from delta_bot.policy import TargetPositions


class _FakeKuCoinClient:
    def __init__(self, has_auth: bool = True):
        self._has_auth = has_auth
        self.spot_orders = []
        self.futures_orders = []

    @property
    def has_auth(self) -> bool:
        return self._has_auth

    def get_spot_candles(self, symbol: str, candle_type: str):
        # Spot format: [time, open, close, high, low, volume, turnover]
        rows = []
        px = 1.20
        for i in range(1, 40):
            px = px * 1.0025
            rows.append(
                [
                    str(1700000000 + i * 900),
                    f"{px * 0.998:.6f}",
                    f"{px:.6f}",
                    f"{px * 1.002:.6f}",
                    f"{px * 0.997:.6f}",
                    "1000",
                    "1200",
                ]
            )
        return rows

    def get_futures_candles(self, symbol: str, granularity: int):
        return [[1700000000000, 1.25, 1.27, 1.24, 1.26, 10000, 12000]]

    def get_spot_ticker(self, symbol: str):
        return {"price": "1.30"}

    def get_futures_ticker(self, symbol: str):
        return {"price": "1.301"}

    def get_spot_account_balance(self, currency: str, account_type: str = "trade"):
        if currency == "USDT":
            return 15.0
        return 0.0

    def get_futures_position_contracts(self, symbol: str):
        return 0

    def get_futures_account_equity(self, currency: str = "USDT"):
        return 0.0

    def place_spot_market_order(self, symbol: str, side: str, size: float):
        self.spot_orders.append((symbol, side, size))
        return {"orderId": f"spot_{len(self.spot_orders)}"}

    def place_futures_market_order(self, symbol: str, side: str, contracts: int):
        self.futures_orders.append((symbol, side, contracts))
        return {"orderId": f"fut_{len(self.futures_orders)}"}


class LiveExecutionTests(unittest.TestCase):
    def test_live_mode_submits_orders(self) -> None:
        fake = _FakeKuCoinClient(has_auth=True)
        state_file = ROOT / "tests" / "_live_state_test.json"
        log_file = ROOT / "tests" / "live_orders.jsonl"
        forced_target = TargetPositions(
            z_score=0.3,
            target_spot_notional_usdt=0.26,
            target_spot_qty=0.2,
            target_futures_contracts=-2,
            target_futures_base_qty=-0.2,
            target_net_delta_base=0.0,
        )
        try:
            with patch("delta_bot.live.KuCoinRestClient.from_env", return_value=fake), patch(
                "delta_bot.live.compute_target_positions", return_value=forced_target
            ):
                result = run_once(
                    config_path=ROOT / "config" / "micro_near_v1.json",
                    mode="live",
                    state_file=state_file,
                    expected_slippage_bps=1.0,
                )
            self.assertTrue(result.risk.allowed)
            self.assertGreater(len(result.planned_orders), 0)
            self.assertGreater(len(result.sent_orders), 0)
            self.assertGreater(len(fake.spot_orders), 0)
            self.assertGreater(len(fake.futures_orders), 0)
            self.assertTrue(log_file.exists())
            line = log_file.read_text(encoding="utf-8").strip().splitlines()[-1]
            payload = json.loads(line)
            self.assertGreater(len(payload["sent_orders"]), 0)
        finally:
            if state_file.exists():
                state_file.unlink()
            if log_file.exists():
                log_file.unlink()

    def test_live_mode_requires_auth(self) -> None:
        fake = _FakeKuCoinClient(has_auth=False)
        state_file = ROOT / "tests" / "_live_state_test_2.json"
        log_file = ROOT / "tests" / "live_orders.jsonl"
        forced_target = TargetPositions(
            z_score=0.3,
            target_spot_notional_usdt=0.26,
            target_spot_qty=0.2,
            target_futures_contracts=-2,
            target_futures_base_qty=-0.2,
            target_net_delta_base=0.0,
        )
        try:
            with patch("delta_bot.live.KuCoinRestClient.from_env", return_value=fake), patch(
                "delta_bot.live.compute_target_positions", return_value=forced_target
            ):
                with self.assertRaises(KuCoinApiError):
                    run_once(
                        config_path=ROOT / "config" / "micro_near_v1.json",
                        mode="live",
                        state_file=state_file,
                        expected_slippage_bps=1.0,
                    )
        finally:
            if state_file.exists():
                state_file.unlink()
            if log_file.exists():
                log_file.unlink()


if __name__ == "__main__":
    unittest.main()
