from __future__ import annotations

from dataclasses import dataclass

from .config import RiskLimitsConfig
from .math_utils import bps


@dataclass(frozen=True)
class RiskContext:
    equity_usdt: float
    peak_equity_usdt: float
    daily_pnl_usdt: float
    current_spot_qty: float
    current_futures_contracts: int
    spot_price: float
    futures_price: float
    futures_multiplier_base: float
    api_error_streak: int
    expected_slippage_bps: float


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


class RiskEngine:
    def __init__(self, cfg: RiskLimitsConfig):
        self.cfg = cfg

    @staticmethod
    def gross_notional_usdt(
        spot_qty: float, fut_contracts: int, spot_price: float, fut_price: float, multiplier: float
    ) -> float:
        spot_notional = abs(spot_qty) * spot_price
        fut_notional = abs(fut_contracts) * fut_price * multiplier
        return spot_notional + fut_notional

    @staticmethod
    def net_delta_notional_usdt(
        spot_qty: float, fut_contracts: int, spot_price: float, multiplier: float
    ) -> float:
        net_base = spot_qty + fut_contracts * multiplier
        return net_base * spot_price

    def evaluate(
        self,
        ctx: RiskContext,
        target_spot_qty: float,
        target_futures_contracts: int,
        is_new_entry: bool = True,
    ) -> RiskDecision:
        if ctx.equity_usdt <= 0:
            return RiskDecision(False, "Equity is non-positive")

        if ctx.api_error_streak >= self.cfg.max_consecutive_api_errors:
            return RiskDecision(False, "API error streak kill switch triggered")

        drawdown_usdt = max(0.0, ctx.peak_equity_usdt - ctx.equity_usdt)
        if drawdown_usdt >= self.cfg.kill_switch_drawdown_usdt:
            return RiskDecision(False, "Drawdown kill switch triggered")

        if -ctx.daily_pnl_usdt >= self.cfg.max_daily_loss_usdt:
            return RiskDecision(False, "Max daily loss reached")

        spread_bps = bps(ctx.spot_price, ctx.futures_price)
        if is_new_entry and spread_bps > self.cfg.max_spread_for_entry_bps:
            return RiskDecision(False, "Spread too wide for new entry")

        if ctx.expected_slippage_bps > self.cfg.max_slippage_bps:
            return RiskDecision(False, "Expected slippage too high")

        gross_notional = self.gross_notional_usdt(
            target_spot_qty,
            target_futures_contracts,
            ctx.spot_price,
            ctx.futures_price,
            ctx.futures_multiplier_base,
        )
        if gross_notional > self.cfg.max_gross_notional_usdt:
            return RiskDecision(False, "Gross notional limit exceeded")

        net_delta_usdt = self.net_delta_notional_usdt(
            target_spot_qty,
            target_futures_contracts,
            ctx.spot_price,
            ctx.futures_multiplier_base,
        )
        if abs(net_delta_usdt) > self.cfg.hard_net_delta_limit_usdt:
            return RiskDecision(False, "Hard net-delta limit exceeded")

        # Approximate futures leverage in notional/equity terms.
        futures_notional = (
            abs(target_futures_contracts) * ctx.futures_price * ctx.futures_multiplier_base
        )
        effective_futures_leverage = futures_notional / ctx.equity_usdt
        if effective_futures_leverage > self.cfg.max_futures_leverage:
            return RiskDecision(False, "Futures leverage limit exceeded")

        return RiskDecision(True, "OK")
