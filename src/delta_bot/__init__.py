"""Core components for a micro-account delta-neutral KuCoin bot."""

from .config import BotConfig, load_config
from .execution import ExecutionPlanner, PlannedOrder
from .kucoin_client import KuCoinApiError, KuCoinCredentials, KuCoinRestClient
from .policy import TargetPositions, compute_target_positions_from_basis_zscore
from .reward import RewardInputs, compute_reward
from .risk import RiskContext, RiskDecision, RiskEngine
from .signal import BasisZscoreSignalOutput, SignalOutput, naive_signal_from_spot_candles
from .state_store import JsonStateStore, RuntimeState

__all__ = [
    "BotConfig",
    "ExecutionPlanner",
    "JsonStateStore",
    "KuCoinApiError",
    "KuCoinCredentials",
    "KuCoinRestClient",
    "PlannedOrder",
    "RiskContext",
    "RiskDecision",
    "RiskEngine",
    "RewardInputs",
    "RuntimeState",
    "BasisZscoreSignalOutput",
    "SignalOutput",
    "TargetPositions",
    "compute_reward",
    "compute_target_positions_from_basis_zscore",
    "load_config",
    "naive_signal_from_spot_candles",
]
