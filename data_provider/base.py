"""
数据提供者抽象基类与标准数据结构
规范不同数据源（AKShare, Baostock, CSV/本地文件）的统一输出契约
统一规范:
1. 日期格式: 'YYYY-MM-DD'，升序排列且无重复
2. 价格单位: 人民币元 (float)
3. 成交量单位: 统一规范为【股】(shares, float/int)，禁止手与股混用
4. 成交额单位: 人民币元 (amount, float)
5. 复权类型: 明确标明 'qfq' (前复权), 'hfq' (后复权), 'none' (不复权)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import pandas as pd


@dataclass
class StockQuoteItem:
    symbol: str
    name: str
    price: float
    pct_chg: float
    volume_shares: float  # 成交量 (股)
    amount: float  # 成交额 (元)
    turnover_rate: float
    pe_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    update_time: str = ""
    source: str = ""


@dataclass
class DataQualityReport:
    symbol: str
    source: str
    fetch_time: str
    trade_date: str
    coverage_ratio: float  # 0.0 ~ 1.0 (非空完整率)
    total_bars: int
    is_fallback: bool
    missing_fields: List[str]
    warnings: List[str]


class BaseDataProvider(ABC):
    """数据源适配器基类"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_stock_list(self) -> List[Dict[str, Any]]:
        """获取全市场股票基本信息列表 [{'symbol': '600519', 'name': '贵州茅台', 'board': 'SH_MAIN'}, ...]"""
        pass

    @abstractmethod
    def get_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        获取历史日 K 线数据
        返回 DataFrame 必须包含标准列:
        ['date', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg', 'turnover']
        其中 volume 必须已归一化为【股】
        """
        pass

    @abstractmethod
    def get_spot_quote(self, symbol: str) -> Optional[StockQuoteItem]:
        """获取单只股票最新行情快照"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查当前数据源可用性与连通性"""
        pass
