from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import List


def spot_candle_type_from_minutes(minutes: int) -> str:
    mapping = {
        1: "1min",
        3: "3min",
        5: "5min",
        15: "15min",
        30: "30min",
        60: "1hour",
        120: "2hour",
        240: "4hour",
        360: "6hour",
        480: "8hour",
        720: "12hour",
        1440: "1day",
        10080: "1week",
    }
    if minutes not in mapping:
        raise ValueError(f"Unsupported spot timeframe minutes: {minutes}")
    return mapping[minutes]


def futures_granularity_from_minutes(minutes: int) -> int:
    supported = {1, 5, 15, 30, 60, 120, 240, 480, 720, 1440, 10080}
    if minutes not in supported:
        raise ValueError(f"Unsupported futures granularity minutes: {minutes}")
    return minutes


def _sorted_spot_candles(candles: List[List[str]]) -> List[List[str]]:
    # Spot format: [time, open, close, high, low, volume, turnover]
    return sorted(candles, key=lambda row: int(row[0]))


def extract_spot_closes(candles: List[List[str]]) -> List[float]:
    sorted_rows = _sorted_spot_candles(candles)
    return [float(row[2]) for row in sorted_rows]


def compute_log_returns(prices: List[float]) -> List[float]:
    out: List[float] = []
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        cur = prices[i]
        if prev <= 0 or cur <= 0:
            continue
        out.append(math.log(cur / prev))
    return out


@dataclass(frozen=True)
class SignalOutput:
    ret_hat: float
    sigma_hat: float
    closes: List[float]
    returns: List[float]


def naive_signal_from_spot_candles(
    candles: List[List[str]],
    min_history: int = 20,
    sigma_floor: float = 1e-4,
) -> SignalOutput:
    closes = extract_spot_closes(candles)
    if len(closes) < min_history + 1:
        raise ValueError("Not enough candle history for signal")

    returns = compute_log_returns(closes)
    if not returns:
        raise ValueError("No valid returns from candles")

    ret_hat = returns[-1]
    if len(returns) >= min_history:
        sigma_hat = statistics.pstdev(returns[-min_history:])
    else:
        sigma_hat = statistics.pstdev(returns)
    sigma_hat = max(sigma_hat, sigma_floor)

    return SignalOutput(
        ret_hat=ret_hat,
        sigma_hat=sigma_hat,
        closes=closes,
        returns=returns,
    )
