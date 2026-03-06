from __future__ import annotations

from dataclasses import dataclass

from .config import DeltaNeutralConfig, InstrumentsConfig, PolicyConfig
from .math_utils import floor_to_step


@dataclass(frozen=True)
class TargetPositions:
    z_score: float
    target_spot_notional_usdt: float
    target_spot_qty: float
    target_futures_contracts: int
    target_futures_base_qty: float
    target_net_delta_base: float


FLAT = "FLAT"
LONG_SPOT_SHORT_FUT = "LONG_SPOT_SHORT_FUT"


@dataclass(frozen=True)
class PolicyState:
    regime: str
    reason: str


def infer_policy_regime(
    *,
    current_spot_qty: float,
    current_futures_contracts: int,
) -> PolicyState:
    if current_spot_qty > 0 and current_futures_contracts < 0:
        return PolicyState(regime=LONG_SPOT_SHORT_FUT, reason="paired_position")
    return PolicyState(regime=FLAT, reason="no_paired_position")


def _entry_target_for_long_spot_short_fut(
    *,
    spot_price: float,
    max_spot_notional_usdt: float,
    policy_cfg: PolicyConfig,
    instr_cfg: InstrumentsConfig,
    basis_z: float,
) -> TargetPositions:
    if spot_price <= 0:
        raise ValueError("spot_price must be > 0")

    raw_spot_qty = max_spot_notional_usdt / spot_price
    raw_spot_qty = floor_to_step(raw_spot_qty, instr_cfg.spot_base_increment)
    if raw_spot_qty <= 0:
        return TargetPositions(
            z_score=basis_z,
            target_spot_notional_usdt=0.0,
            target_spot_qty=0.0,
            target_futures_contracts=0,
            target_futures_base_qty=0.0,
            target_net_delta_base=0.0,
        )

    if (not policy_cfg.allow_spot_short) and raw_spot_qty < 0:
        raw_spot_qty = 0.0

    target_fut_base_raw = policy_cfg.target_hedge_ratio * raw_spot_qty
    target_contracts = int(round(target_fut_base_raw / instr_cfg.futures_multiplier_base))
    target_contracts = int(
        floor_to_step(float(target_contracts), float(instr_cfg.futures_contract_step))
    )
    target_fut_base = target_contracts * instr_cfg.futures_multiplier_base

    if policy_cfg.target_hedge_ratio != 0:
        spot_qty = target_fut_base / policy_cfg.target_hedge_ratio
    else:
        spot_qty = raw_spot_qty
    if (not policy_cfg.allow_spot_short) and spot_qty < 0:
        spot_qty = 0.0
        target_contracts = 0
        target_fut_base = 0.0

    spot_qty = floor_to_step(spot_qty, instr_cfg.spot_base_increment)
    target_notional = spot_qty * spot_price

    if abs(target_notional) < instr_cfg.spot_min_funds_usdt:
        spot_qty = 0.0
        target_notional = 0.0
        target_contracts = 0
        target_fut_base = 0.0

    net_delta_base = spot_qty + target_fut_base
    return TargetPositions(
        z_score=basis_z,
        target_spot_notional_usdt=target_notional,
        target_spot_qty=spot_qty,
        target_futures_contracts=target_contracts,
        target_futures_base_qty=target_fut_base,
        target_net_delta_base=net_delta_base,
    )


def compute_target_positions_from_basis_zscore(
    *,
    basis_z: float,
    spot_price: float,
    current_spot_qty: float,
    current_futures_contracts: int,
    policy_cfg: PolicyConfig,
    instr_cfg: InstrumentsConfig,
    delta_cfg: DeltaNeutralConfig,
) -> TargetPositions:
    state = infer_policy_regime(
        current_spot_qty=current_spot_qty,
        current_futures_contracts=current_futures_contracts,
    )

    if state.regime == FLAT:
        if basis_z > float(delta_cfg.entry_z):
            return _entry_target_for_long_spot_short_fut(
                spot_price=spot_price,
                max_spot_notional_usdt=float(delta_cfg.max_spot_notional_usdt),
                policy_cfg=policy_cfg,
                instr_cfg=instr_cfg,
                basis_z=basis_z,
            )
        return TargetPositions(
            z_score=basis_z,
            target_spot_notional_usdt=0.0,
            target_spot_qty=0.0,
            target_futures_contracts=0,
            target_futures_base_qty=0.0,
            target_net_delta_base=0.0,
        )

    if abs(basis_z) < float(delta_cfg.exit_z):
        return TargetPositions(
            z_score=basis_z,
            target_spot_notional_usdt=0.0,
            target_spot_qty=0.0,
            target_futures_contracts=0,
            target_futures_base_qty=0.0,
            target_net_delta_base=0.0,
        )

    target_fut_base = current_futures_contracts * instr_cfg.futures_multiplier_base
    net_delta_base = current_spot_qty + target_fut_base
    return TargetPositions(
        z_score=basis_z,
        target_spot_notional_usdt=current_spot_qty * spot_price,
        target_spot_qty=current_spot_qty,
        target_futures_contracts=current_futures_contracts,
        target_futures_base_qty=target_fut_base,
        target_net_delta_base=net_delta_base,
    )
