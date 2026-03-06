from __future__ import annotations

from dataclasses import dataclass

from .config import InstrumentsConfig, PolicyConfig
from .math_utils import clip, floor_to_step


@dataclass(frozen=True)
class TargetPositions:
    z_score: float
    target_spot_notional_usdt: float
    target_spot_qty: float
    target_futures_contracts: int
    target_futures_base_qty: float
    target_net_delta_base: float


def compute_target_positions(
    ret_hat: float,
    sigma_hat: float,
    spot_price: float,
    policy_cfg: PolicyConfig,
    instr_cfg: InstrumentsConfig,
) -> TargetPositions:
    if spot_price <= 0:
        raise ValueError("spot_price must be > 0")

    raw_z = ret_hat / (sigma_hat + policy_cfg.epsilon)
    z = clip(raw_z, -policy_cfg.z_clip, policy_cfg.z_clip)

    target_notional = z * policy_cfg.n_side_max_usdt
    if (not policy_cfg.allow_spot_short) and target_notional < 0:
        target_notional = 0.0

    raw_spot_qty = target_notional / spot_price
    spot_qty = floor_to_step(raw_spot_qty, instr_cfg.spot_base_increment)
    if abs(spot_qty * spot_price) < instr_cfg.spot_min_funds_usdt:
        spot_qty = 0.0
        target_notional = 0.0
    else:
        target_notional = spot_qty * spot_price

    target_fut_base = policy_cfg.target_hedge_ratio * spot_qty
    target_contracts = int(round(target_fut_base / instr_cfg.futures_multiplier_base))
    target_contracts = int(
        floor_to_step(float(target_contracts), float(instr_cfg.futures_contract_step))
    )
    target_fut_base = target_contracts * instr_cfg.futures_multiplier_base

    # Align spot target to futures contract granularity to keep hedge legs matched.
    if policy_cfg.target_hedge_ratio != 0:
        aligned_spot_qty = target_fut_base / policy_cfg.target_hedge_ratio
        if (not policy_cfg.allow_spot_short) and aligned_spot_qty < 0:
            aligned_spot_qty = 0.0
            target_contracts = 0
            target_fut_base = 0.0
        spot_qty = floor_to_step(aligned_spot_qty, instr_cfg.spot_base_increment)
        target_notional = spot_qty * spot_price

    if abs(target_notional) < instr_cfg.spot_min_funds_usdt:
        spot_qty = 0.0
        target_notional = 0.0
        target_contracts = 0
        target_fut_base = 0.0

    net_delta_base = spot_qty + target_fut_base
    return TargetPositions(
        z_score=z,
        target_spot_notional_usdt=target_notional,
        target_spot_qty=spot_qty,
        target_futures_contracts=target_contracts,
        target_futures_base_qty=target_fut_base,
        target_net_delta_base=net_delta_base,
    )
