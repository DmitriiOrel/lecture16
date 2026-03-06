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


@dataclass(frozen=True)
class LstmBacktestMetrics:
    mae: float
    rmse: float
    mape: float
    points: int


@dataclass(frozen=True)
class LstmGarchSignalOutput:
    ret_hat: float
    sigma_hat: float
    closes: List[float]
    returns: List[float]
    forecast_price: float
    direction: int
    forecast_horizon: int
    window: int
    backtest: LstmBacktestMetrics
    signal_model: str


def _candles_to_feature_frame(candles: List[List[str]]):
    import pandas as pd

    rows = _sorted_spot_candles(candles)
    frame = pd.DataFrame(
        rows,
        columns=["time", "open", "close", "high", "low", "volume", "turnover"],
    )
    for col in ["open", "high", "low", "close", "volume", "turnover"]:
        frame[col] = frame[col].astype("float64")
    frame["ts"] = pd.to_datetime(frame["time"].astype("int64"), unit="s", utc=True)
    frame = frame.set_index("ts")

    feat = frame.copy()
    feat["ret_1"] = feat["close"].pct_change(1)
    feat["ret_3"] = feat["close"].pct_change(3)
    feat["ma_5"] = feat["close"].rolling(5).mean()
    feat["ma_10"] = feat["close"].rolling(10).mean()
    feat["ma_20"] = feat["close"].rolling(20).mean()
    feat["hl_range"] = (feat["high"] - feat["low"]) / feat["close"]
    feat["oc_change"] = (feat["close"] - feat["open"]) / feat["open"]
    feat["vol_chg_1"] = feat["volume"].pct_change(1)

    feature_cols = [
        "close",
        "volume",
        "ret_1",
        "ret_3",
        "ma_5",
        "ma_10",
        "ma_20",
        "hl_range",
        "oc_change",
        "vol_chg_1",
    ]
    data_feat = feat[feature_cols].dropna().copy()
    return frame, data_feat, feature_cols


def _build_lstm_windows(data_feat, feature_cols: List[str], window: int, forecast_horizon: int):
    import numpy as np
    import pandas as pd

    x_values = data_feat[feature_cols].to_numpy(dtype="float32")
    y_values = data_feat["close"].to_numpy(dtype="float32")
    dates = data_feat.index

    x_all: List[object] = []
    y_all: List[float] = []
    idx_all: List[object] = []

    for i in range(window, len(x_values) - forecast_horizon + 1):
        x_all.append(x_values[i - window : i, :])
        target_pos = i + forecast_horizon - 1
        y_all.append(float(y_values[target_pos]))
        idx_all.append(dates[target_pos])

    x_all_arr = np.asarray(x_all, dtype="float32")
    y_all_arr = np.asarray(y_all, dtype="float32")
    idx = pd.DatetimeIndex(idx_all)
    return x_all_arr, y_all_arr, idx


def _compute_garch_sigma_from_returns(
    returns: List[float],
    sigma_floor: float,
    garch_p: int,
    garch_q: int,
) -> float:
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
        return max(math.sqrt(max(var_1, 0.0)) / 100.0, float(sigma_floor))
    except Exception:
        return max(
            statistics.pstdev(returns[-min(len(returns), 120) :]),
            float(sigma_floor),
        )


def lstm_garch_signal_from_spot_candles(
    candles: List[List[str]],
    forecast_horizon: int = 5,
    window: int = 30,
    min_history: int = 240,
    train_frac: float = 0.7,
    valid_frac: float = 0.15,
    lstm_units: int = 32,
    epochs: int = 30,
    batch_size: int = 32,
    patience: int = 8,
    random_seed: int = 42,
    sigma_floor: float = 1e-4,
    garch_p: int = 1,
    garch_q: int = 1,
) -> LstmGarchSignalOutput:
    import numpy as np

    horizon = max(int(forecast_horizon), 1)
    win = max(int(window), 5)

    frame, data_feat, feature_cols = _candles_to_feature_frame(candles)
    closes = [float(x) for x in frame["close"].tolist()]
    returns = compute_log_returns(closes)

    if len(data_feat) < max(min_history, win + horizon + 30):
        raise ValueError("Not enough candle history for LSTM/GARCH signal")
    if len(returns) < 20:
        raise ValueError("Not enough returns history for GARCH signal")

    x_all, y_all, _idx_all = _build_lstm_windows(
        data_feat=data_feat,
        feature_cols=feature_cols,
        window=win,
        forecast_horizon=horizon,
    )
    if len(x_all) < 30:
        raise ValueError("Not enough supervised windows for LSTM signal")

    n = len(x_all)
    train_end = max(int(n * float(train_frac)), 1)
    valid_end = max(int(n * float(train_frac + valid_frac)), train_end + 1)
    valid_end = min(valid_end, n - 1)
    if train_end >= valid_end:
        raise ValueError("Invalid train/valid split for LSTM signal")

    x_train = x_all[:train_end]
    y_train = y_all[:train_end]
    x_valid = x_all[train_end:valid_end]
    y_valid = y_all[train_end:valid_end]

    x_mean = x_train.mean(axis=(0, 1), keepdims=True)
    x_std = x_train.std(axis=(0, 1), keepdims=True) + 1e-8
    y_mean = float(y_train.mean())
    y_std = float(y_train.std() + 1e-8)

    x_train_scaled = ((x_train - x_mean) / x_std).astype("float32")
    x_valid_scaled = ((x_valid - x_mean) / x_std).astype("float32")
    y_train_scaled = ((y_train - y_mean) / y_std).astype("float32")

    backtest_mae = 0.0
    backtest_rmse = 0.0
    backtest_mape = 0.0
    signal_model = "lstm_garch_ref"

    try:
        import tensorflow as tf

        tf.keras.utils.set_random_seed(int(random_seed))
        model = tf.keras.Sequential(
            [
                tf.keras.layers.Input(shape=(win, x_train_scaled.shape[2])),
                tf.keras.layers.LSTM(int(lstm_units)),
                tf.keras.layers.Dense(1),
            ]
        )
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
            loss="mse",
            metrics=["mae"],
        )
        es = tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=max(int(patience), 1),
            restore_best_weights=True,
        )
        model.fit(
            x_train_scaled,
            y_train_scaled,
            validation_data=(x_valid_scaled, ((y_valid - y_mean) / y_std).astype("float32")),
            epochs=max(int(epochs), 1),
            batch_size=max(int(batch_size), 1),
            verbose=0,
            callbacks=[es],
            shuffle=False,
        )

        y_valid_pred_scaled = model.predict(x_valid_scaled, verbose=0).ravel()
        y_valid_pred = y_valid_pred_scaled * y_std + y_mean
        valid_err = y_valid - y_valid_pred
        backtest_mae = float(np.mean(np.abs(valid_err)))
        backtest_rmse = float(np.sqrt(np.mean(valid_err**2)))
        denom = np.where(np.abs(y_valid) > 1e-12, np.abs(y_valid), np.nan)
        backtest_mape = float(np.nanmean(np.abs(valid_err) / denom))

        last_window = data_feat[feature_cols].iloc[-win:].to_numpy(dtype="float32")
        last_window_scaled = ((last_window[None, :, :] - x_mean) / x_std).astype("float32")
        forecast_scaled = float(model.predict(last_window_scaled, verbose=0).ravel()[0])
        forecast_price = float(forecast_scaled * y_std + y_mean)
    except Exception:
        # Fallback if tensorflow is unavailable: use last observed return trend.
        signal_model = "lstm_unavailable_fallback"
        fallback_ret = float(statistics.mean(returns[-min(len(returns), 20) :]))
        last_close = float(data_feat["close"].iloc[-1])
        forecast_price = float(last_close * math.exp(fallback_ret * horizon))
        # Baseline metrics on validation split by lag-1 close in window.
        y_valid_baseline = x_valid[:, -1, 0]
        valid_err = y_valid - y_valid_baseline
        backtest_mae = float(np.mean(np.abs(valid_err)))
        backtest_rmse = float(np.sqrt(np.mean(valid_err**2)))
        denom = np.where(np.abs(y_valid) > 1e-12, np.abs(y_valid), np.nan)
        backtest_mape = float(np.nanmean(np.abs(valid_err) / denom))

    last_close = float(data_feat["close"].iloc[-1])
    if forecast_price <= 0 or last_close <= 0:
        raise ValueError("Invalid LSTM forecast/close values")

    ret_hat = math.log(forecast_price / last_close) / horizon
    sigma_hat = _compute_garch_sigma_from_returns(
        returns=returns,
        sigma_floor=sigma_floor,
        garch_p=garch_p,
        garch_q=garch_q,
    )
    direction = 1 if forecast_price > last_close else -1

    return LstmGarchSignalOutput(
        ret_hat=float(ret_hat),
        sigma_hat=float(sigma_hat),
        closes=closes,
        returns=returns,
        forecast_price=float(forecast_price),
        direction=direction,
        forecast_horizon=horizon,
        window=win,
        backtest=LstmBacktestMetrics(
            mae=float(backtest_mae),
            rmse=float(backtest_rmse),
            mape=float(backtest_mape),
            points=int(len(y_valid)),
        ),
        signal_model=signal_model,
    )
