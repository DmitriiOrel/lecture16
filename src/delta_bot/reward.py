from __future__ import annotations

from dataclasses import dataclass

from .config import RewardConfig


@dataclass(frozen=True)
class RewardInputs:
    pnl_usdt: float
    fee_usdt: float
    funding_usdt: float
    net_delta_notional_usdt: float
    delta_contracts: int
    drawdown_fraction: float


def compute_reward(inputs: RewardInputs, reward_cfg: RewardConfig) -> float:
    drawdown_penalty = max(0.0, inputs.drawdown_fraction - reward_cfg.drawdown_soft) ** 2

    return (
        (inputs.pnl_usdt - inputs.fee_usdt + inputs.funding_usdt)
        - reward_cfg.lambda_delta * abs(inputs.net_delta_notional_usdt)
        - reward_cfg.lambda_turnover * abs(inputs.delta_contracts)
        - reward_cfg.lambda_dd * drawdown_penalty
    )
