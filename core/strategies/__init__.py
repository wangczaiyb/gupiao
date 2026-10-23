from core.strategies.base import BaseStrategy, SignalType, StrategySignal
from core.strategies.trend_pullback import TrendPullbackStrategy
from core.strategies.range_breakout import RangeBreakoutStrategy

AVAILABLE_STRATEGIES = {
    "trend_pullback": TrendPullbackStrategy,
    "range_breakout": RangeBreakoutStrategy,
}

__all__ = [
    "BaseStrategy",
    "SignalType",
    "StrategySignal",
    "TrendPullbackStrategy",
    "RangeBreakoutStrategy",
    "AVAILABLE_STRATEGIES",
]
