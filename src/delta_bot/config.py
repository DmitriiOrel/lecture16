from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class TimingConfig:
    data_tf_minutes: int
    rebalance_tf_minutes: int


@dataclass(frozen=True)
class InstrumentsConfig:
    spot_symbol: str
    futures_symbol: str
    futures_multiplier_base: float
    spot_base_increment: float
    spot_min_funds_usdt: float
    futures_contract_step: int
    spot_min_size_base: float = 0.0


@dataclass(frozen=True)
class ActionConfig:
    type: str
    space: List[int]
    contract_step: int
    max_abs_contracts: int


@dataclass(frozen=True)
class PolicyConfig:
    epsilon: float
    allow_spot_short: bool
    target_hedge_ratio: float
    z_clip: float = 2.0
    n_side_max_usdt: float = 1.5
    kelly_z_scale: float = 1.0


@dataclass(frozen=True)
class RewardConfig:
    formula: str
    lambda_delta: float
    lambda_turnover: float
    lambda_dd: float
    drawdown_soft: float


@dataclass(frozen=True)
class RiskLimitsConfig:
    max_gross_notional_usdt: float
    max_single_order_notional_usdt: float
    max_futures_leverage: float
    target_net_delta_band_usdt: float
    hard_net_delta_limit_usdt: float
    max_daily_loss_usdt: float
    kill_switch_drawdown_usdt: float
    max_slippage_bps: float
    max_spread_for_entry_bps: float
    max_consecutive_api_errors: int


@dataclass(frozen=True)
class ExecutionConfig:
    order_type: str
    slice_orders: bool
    max_retries: int


@dataclass(frozen=True)
class AccountConfig:
    equity_usdt: float


@dataclass(frozen=True)
class StateConfig:
    features: List[str]


@dataclass(frozen=True)
class SignalConfig:
    model: str
    arima_order: List[int]
    forecast_horizon: int
    min_history: int
    window: int
    train_frac: float
    valid_frac: float
    lstm_units: int
    epochs: int
    batch_size: int
    patience: int
    random_seed: int
    sigma_floor: float
    garch_p: int
    garch_q: int
    backtest_points: int


@dataclass(frozen=True)
class DeltaNeutralConfig:
    basis_window: int
    entry_z: float
    exit_z: float
    max_spot_notional_usdt: float
    mode: str = "long_spot_short_futures_only"


@dataclass(frozen=True)
class BotConfig:
    version: str
    account: AccountConfig
    timing: TimingConfig
    instruments: InstrumentsConfig
    state: StateConfig
    signal: SignalConfig
    delta_neutral: DeltaNeutralConfig
    action: ActionConfig
    policy: PolicyConfig
    reward: RewardConfig
    risk_limits: RiskLimitsConfig
    execution: ExecutionConfig


def _require(data: Dict[str, Any], key: str) -> Any:
    if key not in data:
        raise KeyError(f"Missing required config key: {key}")
    return data[key]


def _load_signal_config(data: Dict[str, Any]) -> SignalConfig:
    raw = data.get("signal", {})
    return SignalConfig(
        model=raw.get("model", "basis_zscore"),
        arima_order=list(raw.get("arima_order", [1, 1, 2])),
        forecast_horizon=int(raw.get("forecast_horizon", 5)),
        min_history=int(raw.get("min_history", 120)),
        window=int(raw.get("window", 30)),
        train_frac=float(raw.get("train_frac", 0.7)),
        valid_frac=float(raw.get("valid_frac", 0.15)),
        lstm_units=int(raw.get("lstm_units", 32)),
        epochs=int(raw.get("epochs", 30)),
        batch_size=int(raw.get("batch_size", 32)),
        patience=int(raw.get("patience", 8)),
        random_seed=int(raw.get("random_seed", 42)),
        sigma_floor=float(raw.get("sigma_floor", 1e-4)),
        garch_p=int(raw.get("garch_p", 1)),
        garch_q=int(raw.get("garch_q", 1)),
        backtest_points=int(raw.get("backtest_points", 120)),
    )


def load_config(path: str | Path) -> BotConfig:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    return BotConfig(
        version=_require(data, "version"),
        account=AccountConfig(**_require(data, "account")),
        timing=TimingConfig(**_require(data, "timing")),
        instruments=InstrumentsConfig(**_require(data, "instruments")),
        state=StateConfig(**_require(data, "state")),
        signal=_load_signal_config(data),
        delta_neutral=DeltaNeutralConfig(
            **data.get(
                "delta_neutral",
                {
                    "basis_window": int(data.get("signal", {}).get("window", 30)),
                    "entry_z": 1.5,
                    "exit_z": 0.3,
                    "max_spot_notional_usdt": 1.0,
                    "mode": "long_spot_short_futures_only",
                },
            )
        ),
        action=ActionConfig(**_require(data, "action")),
        policy=PolicyConfig(**_require(data, "policy")),
        reward=RewardConfig(**_require(data, "reward")),
        risk_limits=RiskLimitsConfig(**_require(data, "risk_limits")),
        execution=ExecutionConfig(**_require(data, "execution")),
    )
