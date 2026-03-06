from __future__ import annotations

import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from delta_bot.signal import naive_signal_from_spot_candles, spot_candle_type_from_minutes
from delta_bot.state_store import JsonStateStore, RuntimeState


class SignalAndStateTests(unittest.TestCase):
    def test_spot_candle_type(self) -> None:
        self.assertEqual(spot_candle_type_from_minutes(15), "15min")
        self.assertEqual(spot_candle_type_from_minutes(60), "1hour")

    def test_naive_signal(self) -> None:
        # Spot format: [time, open, close, high, low, volume, turnover]
        candles = [
            ["3", "1.0", "1.03", "1.04", "0.99", "100", "100"],
            ["1", "1.0", "1.01", "1.02", "0.99", "100", "100"],
            ["2", "1.01", "1.02", "1.03", "1.00", "100", "100"],
            ["4", "1.03", "1.04", "1.05", "1.02", "100", "100"],
            ["5", "1.04", "1.02", "1.05", "1.01", "100", "100"],
            ["6", "1.02", "1.01", "1.03", "1.00", "100", "100"],
            ["7", "1.01", "1.00", "1.02", "0.99", "100", "100"],
            ["8", "1.00", "1.02", "1.03", "0.99", "100", "100"],
            ["9", "1.02", "1.03", "1.04", "1.01", "100", "100"],
            ["10", "1.03", "1.05", "1.06", "1.02", "100", "100"],
            ["11", "1.05", "1.07", "1.08", "1.04", "100", "100"],
            ["12", "1.07", "1.08", "1.09", "1.06", "100", "100"],
            ["13", "1.08", "1.09", "1.10", "1.07", "100", "100"],
            ["14", "1.09", "1.10", "1.11", "1.08", "100", "100"],
            ["15", "1.10", "1.11", "1.12", "1.09", "100", "100"],
            ["16", "1.11", "1.12", "1.13", "1.10", "100", "100"],
            ["17", "1.12", "1.13", "1.14", "1.11", "100", "100"],
            ["18", "1.13", "1.14", "1.15", "1.12", "100", "100"],
            ["19", "1.14", "1.15", "1.16", "1.13", "100", "100"],
            ["20", "1.15", "1.16", "1.17", "1.14", "100", "100"],
            ["21", "1.16", "1.17", "1.18", "1.15", "100", "100"],
        ]
        sig = naive_signal_from_spot_candles(candles, min_history=20)
        self.assertIsInstance(sig.ret_hat, float)
        self.assertGreater(sig.sigma_hat, 0)
        self.assertEqual(len(sig.closes), 21)

    def test_json_state_store(self) -> None:
        p = ROOT / "tests" / "_state_store_test.json"
        try:
            store = JsonStateStore(p)
            s = store.load(default_equity_usdt=15.0)
            self.assertEqual(s.day_start_equity_usdt, 15.0)
            s.api_error_streak = 2
            store.save(s)

            with p.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            self.assertEqual(raw["api_error_streak"], 2)

            s2 = store.load(default_equity_usdt=1.0)
            self.assertEqual(s2.api_error_streak, 2)
            self.assertIsInstance(s2, RuntimeState)
        finally:
            if p.exists():
                p.unlink()


if __name__ == "__main__":
    unittest.main()
