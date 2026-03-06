from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import List, Sequence, Tuple


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


@dataclass(frozen=True)
class ArimaBacktestMetrics:
    mse: float
    mae: float
    mape: float
    points: int


@dataclass(frozen=True)
class ArimaGarchSignalOutput:
    ret_hat: float
    sigma_hat: float
    closes: List[float]
    returns: List[float]
    forecast_price: float
    direction: int
    arima_order: Tuple[int, int, int]
    forecast_horizon: int
    backtest: ArimaBacktestMetrics


def _normalize_arima_order(order: Sequence[int]) -> Tuple[int, int, int]:
    if len(order) != 3:
        raise ValueError(f"ARIMA order must have 3 ints, got: {order}")
    p, d, q = (int(x) for x in order)
    if min(p, d, q) < 0:
        raise ValueError(f"ARIMA order must be non-negative, got: {order}")
    return p, d, q


def _closes_to_series(closes: Sequence[float]):
    import pandas as pd

    return pd.Series([float(x) for x in closes], dtype="float64")


def arima_backtest_overlay_from_closes(
    closes: Sequence[float],
    arima_order: Sequence[int] = (1, 1, 2),
    backtest_points: int = 120,
):
    if len(closes) < 20:
        raise ValueError("Not enough close history for ARIMA backtest")
    order = _normalize_arima_order(arima_order)
    close_series = _closes_to_series(closes)
    start_idx = max(order[1], len(close_series) - max(int(backtest_points), 5))

    try:
        from statsmodels.tsa.arima.model import ARIMA

        fitted = ARIMA(close_series, order=order).fit()
        pred_res = fitted.get_prediction(start=start_idx, end=len(close_series) - 1)
        pred = pred_res.predicted_mean.astype("float64")
        conf = pred_res.conf_int(alpha=0.05)
        lower_col, upper_col = conf.columns[0], conf.columns[1]

        overlay = (
            close_series.iloc[start_idx:]
            .to_frame(name="actual_price")
            .join(pred.to_frame(name="predicted_price"), how="inner")
        )
        overlay["lower_price"] = conf[lower_col].reindex(overlay.index)
        overlay["upper_price"] = conf[upper_col].reindex(overlay.index)
    except Exception:
        # Fallback when statsmodels is unavailable: one-step lag baseline.
        overlay = close_series.iloc[start_idx:].to_frame(name="actual_price")
        overlay["predicted_price"] = close_series.shift(1).iloc[start_idx:].values
        overlay["lower_price"] = overlay["predicted_price"]
        overlay["upper_price"] = overlay["predicted_price"]

    err = overlay["actual_price"] - overlay["predicted_price"]

    mse = float((err.pow(2)).mean()) if len(overlay) else 0.0
    mae = float(err.abs().mean()) if len(overlay) else 0.0
    denom = overlay["actual_price"].replace(0.0, float("nan"))
    mape = float((err.abs() / denom).dropna().mean()) if len(overlay) else 0.0
    metrics = ArimaBacktestMetrics(
        mse=mse,
        mae=mae,
        mape=mape,
        points=int(len(overlay)),
    )
    return overlay, metrics


def arima_garch_signal_from_spot_candles(
    candles: List[List[str]],
    arima_order: Sequence[int] = (1, 1, 2),
    forecast_horizon: int = 5,
    min_history: int = 120,
    sigma_floor: float = 1e-4,
    garch_p: int = 1,
    garch_q: int = 1,
    backtest_points: int = 120,
) -> ArimaGarchSignalOutput:
    closes = extract_spot_closes(candles)
    if len(closes) < max(min_history, 30):
        raise ValueError("Not enough candle history for ARIMA/GARCH signal")

    returns = compute_log_returns(closes)
    if len(returns) < 20:
        raise ValueError("Not enough returns history for GARCH signal")

    order = _normalize_arima_order(arima_order)
    horizon = max(int(forecast_horizon), 1)
    close_series = _closes_to_series(closes)

    last_close = float(close_series.iloc[-1])
    if last_close <= 0:
        raise ValueError("Non-positive latest close price")
    try:
        from statsmodels.tsa.arima.model import ARIMA

        arima_fit = ARIMA(close_series, order=order).fit()
        forecast_price = float(arima_fit.forecast(steps=horizon).iloc[-1])
        if forecast_price <= 0:
            raise ValueError("Non-positive ARIMA forecast")
        # Convert forecast in price space into per-step log-return expectation.
        ret_hat = math.log(forecast_price / last_close) / horizon
    except Exception:
        fallback_ret = statistics.mean(returns[-min(len(returns), 20) :])
        ret_hat = fallback_ret
        forecast_price = last_close * math.exp(ret_hat * horizon)

    try:
        from arch import arch_model

        garch_fit = arch_model(
            _closes_to_series(returns) * 100.0,
            mean="Zero",
            vol="GARCH",
            p=max(int(garch_p), 1),
            q=max(int(garch_q), 1),
            dist="normal",
        ).fit(disp="off")
        var_1 = float(garch_fit.forecast(horizon=1).variance.iloc[-1, 0])
        sigma_hat = max(math.sqrt(max(var_1, 0.0)) / 100.0, float(sigma_floor))
    except Exception:
        sigma_hat = max(
            statistics.pstdev(returns[-min(len(returns), 120) :]),
            float(sigma_floor),
        )

    _overlay, backtest = arima_backtest_overlay_from_closes(
        closes=closes,
        arima_order=order,
        backtest_points=backtest_points,
    )

    direction = 1 if forecast_price > last_close else -1
    return ArimaGarchSignalOutput(
        ret_hat=ret_hat,
        sigma_hat=sigma_hat,
        closes=closes,
        returns=returns,
        forecast_price=forecast_price,
        direction=direction,
        arima_order=order,
        forecast_horizon=horizon,
        backtest=backtest,
    )
