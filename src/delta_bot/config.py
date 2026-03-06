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


@dataclass(frozen=True)
class ActionConfig:
    type: str
    space: List[int]
    contract_step: int
    max_abs_contracts: int


@dataclass(frozen=True)
class PolicyConfig:
    epsilon: float
    z_clip: float
    n_side_max_usdt: float
    allow_spot_short: bool
    target_hedge_ratio: float


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
class BotConfig:
    version: str
    account: AccountConfig
    timing: TimingConfig
    instruments: InstrumentsConfig
    state: StateConfig
    action: ActionConfig
    policy: PolicyConfig
    reward: RewardConfig
    risk_limits: RiskLimitsConfig
    execution: ExecutionConfig


def _require(data: Dict[str, Any], key: str) -> Any:
    if key not in data:
        raise KeyError(f"Missing required config key: {key}")
    return data[key]


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
        action=ActionConfig(**_require(data, "action")),
        policy=PolicyConfig(**_require(data, "policy")),
        reward=RewardConfig(**_require(data, "reward")),
        risk_limits=RiskLimitsConfig(**_require(data, "risk_limits")),
        execution=ExecutionConfig(**_require(data, "execution")),
    )
