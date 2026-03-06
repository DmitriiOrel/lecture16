from __future__ import annotations

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


def _normalize_kucoin_ts(raw_ts: str | int | float) -> int:
    ts = int(float(raw_ts))
    if ts > 10**12:
        ts //= 1000
    return ts


def _sorted_spot_candles(candles: List[List[str]]) -> List[List[str]]:
    # Spot format: [time, open, close, high, low, volume, turnover]
    return sorted(candles, key=lambda row: int(row[0]))


def _sorted_futures_candles(candles: List[List[str]]) -> List[List[str]]:
    # Futures format: [time, open, high, low, close, volume, turnover]
    return sorted(candles, key=lambda row: _normalize_kucoin_ts(row[0]))


def _spot_close_map(candles: List[List[str]]) -> dict[int, float]:
    out: dict[int, float] = {}
    for row in _sorted_spot_candles(candles):
        ts = _normalize_kucoin_ts(row[0])
        out[ts] = float(row[2])
    return out


def _futures_close_map(candles: List[List[str]]) -> dict[int, float]:
    out: dict[int, float] = {}
    for row in _sorted_futures_candles(candles):
        ts = _normalize_kucoin_ts(row[0])
        close_idx = 4 if len(row) >= 5 else 2
        out[ts] = float(row[close_idx])
    return out


def extract_spot_closes(candles: List[List[str]]) -> List[float]:
    rows = _sorted_spot_candles(candles)
    return [float(row[2]) for row in rows]


def compute_simple_returns(prices: List[float]) -> List[float]:
    out: List[float] = []
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        cur = prices[i]
        if prev <= 0 or cur <= 0:
            continue
        out.append(cur / prev - 1.0)
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

    returns = compute_simple_returns(closes)
    if not returns:
        raise ValueError("No valid returns from candles")

    ret_hat = returns[-1]
    if len(returns) >= min_history:
        sigma_hat = statistics.pstdev(returns[-min_history:])
    else:
        sigma_hat = statistics.pstdev(returns)
    sigma_hat = max(float(sigma_hat), float(sigma_floor))

    return SignalOutput(
        ret_hat=float(ret_hat),
        sigma_hat=float(sigma_hat),
        closes=closes,
        returns=returns,
    )


@dataclass(frozen=True)
class BasisZscoreSignalOutput:
    basis: float
    basis_mean: float
    basis_std: float
    basis_z: float
    history_points: int
    basis_history: List[float]


def basis_zscore_signal_from_candles(
    spot_candles: List[List[str]],
    futures_candles: List[List[str]],
    *,
    spot_price: float,
    futures_price: float,
    window: int = 60,
    epsilon: float = 1e-8,
) -> BasisZscoreSignalOutput:
    if spot_price <= 0 or futures_price <= 0:
        raise ValueError("spot_price and futures_price must be > 0")

    basis_now = (futures_price - spot_price) / spot_price
    spot_map = _spot_close_map(spot_candles)
    fut_map = _futures_close_map(futures_candles)
    common_ts = sorted(set(spot_map.keys()).intersection(fut_map.keys()))

    basis_history: List[float] = []
    for ts in common_ts:
        s = float(spot_map[ts])
        f = float(fut_map[ts])
        if s <= 0 or f <= 0:
            continue
        basis_history.append((f - s) / s)

    lookback = max(int(window), 5)
    if len(basis_history) < lookback + 1:
        raise ValueError("Not enough overlapping basis history")

    ref = basis_history[-lookback - 1 : -1]
    basis_mean = float(statistics.mean(ref))
    basis_std = float(statistics.pstdev(ref))
    basis_std = max(basis_std, float(epsilon))
    basis_z = (basis_now - basis_mean) / basis_std

    return BasisZscoreSignalOutput(
        basis=float(basis_now),
        basis_mean=float(basis_mean),
        basis_std=float(basis_std),
        basis_z=float(basis_z),
        history_points=int(len(basis_history)),
        basis_history=basis_history,
    )
