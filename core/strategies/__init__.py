from core.strategies.base import BaseStrategy, SignalType, StrategySignal
from core.strategies.trend_pullback import TrendPullbackStrategy
from core.strategies.range_breakout import RangeBreakoutStrategy
from core.strategies.rs_momentum import RSMomentumStrategy
from core.strategies.volatility_contraction import VolatilityContractionStrategy

AVAILABLE_STRATEGIES = {
    "trend_pullback": TrendPullbackStrategy,
    "range_breakout": RangeBreakoutStrategy,
    "rs_momentum": RSMomentumStrategy,
    "volatility_contraction": VolatilityContractionStrategy,
}

__all__ = [
    "BaseStrategy",
    "SignalType",
    "StrategySignal",
    "TrendPullbackStrategy",
    "RangeBreakoutStrategy",
    "RSMomentumStrategy",
    "VolatilityContractionStrategy",
    "AVAILABLE_STRATEGIES",
]

