"""
波段交易策略基类与信号定义
规范策略入场、止损、止盈、条件拆解与风险清单契约
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import pandas as pd


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NONE = "NONE"


@dataclass
class StrategySignal:
    symbol: str
    date: str  # 信号生成基准日 'YYYY-MM-DD' (收盘后产生)
    signal_type: SignalType
    strategy_name: str
    strategy_version: str = "1.0.0"
    candidate_entry_price: float = 0.0  # 建议/候选入场参考价
    stop_loss_price: float = 0.0  # 建议止损价
    take_profit_price: float = 0.0  # 建议止盈价
    stop_loss_rationale: str = ""  # 止损计算依据
    conditions_met: List[str] = field(default_factory=list)  # 已满足条件
    conditions_pending: List[str] = field(default_factory=list)  # 尚未满足/待观察条件
    risks: List[str] = field(default_factory=list)  # 主要风险提示
    metrics: Dict[str, Any] = field(default_factory=dict)  # 当日指标快照
    priority_score: float = 0.0  # 候选信号排序/确定性评分 (用于跨标的资金竞争)

    @property
    def is_actionable(self) -> bool:
        """是否触发有效买入信号"""
        return self.signal_type == SignalType.BUY and len(self.conditions_pending) == 0


class BaseStrategy(ABC):
    """波段策略抽象基类"""

    def __init__(self, name: str, params: Optional[Dict[str, Any]] = None):
        self.name = name
        self.params = params or {}

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, symbol: str) -> List[StrategySignal]:
        """
        为历史时间序列计算信号序列
        输入 df 必须已预计算指标并按日期升序排列
        """
        pass

    @abstractmethod
    def evaluate_latest(self, df: pd.DataFrame, symbol: str) -> StrategySignal:
        """
        评估最新一根 K 线的条件与候选状态
        用于“已满足条件”与“待满足条件”的细化拆解展示
        """
        pass

    @abstractmethod
    def get_description(self) -> Dict[str, Any]:
        """获取策略设计逻辑、参数说明、入场条件与退出条件文档"""
        pass
