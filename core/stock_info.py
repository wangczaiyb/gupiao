"""
A 股证券信息与标的分类模块
正确识别交易所、板块、风险警示状态 (ST, *ST, 退市整理)、停牌及新股标识
提供严谨的标的过滤与多维度股票池筛选能力
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional
from core.rules import classify_symbol, get_board_rules


@dataclass
class StockProfile:
    symbol: str  # 6位标准数字代码，例如 '600519', '300750', '688981', '920211'
    name: str  # 股票简称
    exchange: str  # 'SH', 'SZ', 'BJ'
    board_key: str  # 'SH_MAIN', 'SZ_MAIN', 'CHINEXT', 'STAR', 'BSE'
    board_name: str  # '沪市主板', '深市主板', '创业板', '科创板', '北交所'
    is_st: bool = False  # 是否为 ST 或 *ST 风险警示股票
    is_delisting: bool = False  # 是否处于退市整理期
    is_suspended: bool = False  # 是否停牌
    list_date: Optional[str] = None  # 上市日期 'YYYY-MM-DD'
    industry: str = "其他"  # 所属行业
    total_shares: float = 0.0  # 总股本 (股)
    circulating_shares: float = 0.0  # 流通股本 (股)

    @property
    def full_code(self) -> str:
        """带市场前缀的代码 (如 SH600519, SZ300750, BJ920211)"""
        return f"{self.exchange}{self.symbol}"

    @property
    def risk_tags(self) -> List[str]:
        """风险标签"""
        tags = []
        if self.is_delisting:
            tags.append("退市整理")
        if self.is_st:
            tags.append("风险警示(ST)")
        if self.is_suspended:
            tags.append("停牌")
        if self.name.startswith("N"):
            tags.append("上市首日")
        elif self.name.startswith("C"):
            tags.append("上市次日至第5日")
        return tags


def parse_stock_profile(
    symbol: str,
    name: str,
    is_suspended: bool = False,
    list_date: Optional[str] = None,
    industry: str = "其他",
    total_shares: float = 0.0,
    circulating_shares: float = 0.0,
) -> StockProfile:
    """
    解析并构建标准 StockProfile
    通过简称和板块规则精确识别 ST、退市及交易属性
    """
    clean_sym = symbol.strip().upper()
    if clean_sym.startswith(("SH", "SZ", "BJ")):
        clean_sym = clean_sym[2:].strip(".")
    elif "." in clean_sym:
        parts = clean_sym.split(".")
        clean_sym = parts[0] if parts[0].isdigit() else parts[1]

    board_key, exchange, board_name = classify_symbol(clean_sym)

    # 识别风险警示 (ST, *ST, S*ST, SST)
    name_clean = name.strip()
    is_st = any(st_flag in name_clean for st_flag in ("ST", "*ST", "S*ST", "SST"))
    is_delisting = "退" in name_clean or "退市" in name_clean

    return StockProfile(
        symbol=clean_sym,
        name=name_clean,
        exchange=exchange,
        board_key=board_key,
        board_name=board_name,
        is_st=is_st,
        is_delisting=is_delisting,
        is_suspended=is_suspended,
        list_date=list_date,
        industry=industry,
        total_shares=total_shares,
        circulating_shares=circulating_shares,
    )


def filter_stock_pool(
    stocks: List[StockProfile],
    allowed_boards: Optional[List[str]] = None,
    exclude_st: bool = True,
    exclude_delisting: bool = True,
    exclude_suspended: bool = True,
    min_listing_days: int = 60,
    current_date: Optional[date] = None,
) -> List[StockProfile]:
    """
    可配置的股票池筛选器
    支持按板块、风险状态、停牌、上市时长进行预过滤
    """
    if current_date is None:
        current_date = date.today()

    filtered = []
    for stock in stocks:
        # 板块过滤
        if allowed_boards and stock.board_key not in allowed_boards:
            continue

        # 风险过滤
        if exclude_st and stock.is_st:
            continue
        if exclude_delisting and stock.is_delisting:
            continue
        if exclude_suspended and stock.is_suspended:
            continue

        # 上市时间过滤 (排除次新爆炒期以降低无规律暴跌风险)
        if stock.list_date and min_listing_days > 0:
            try:
                list_dt = datetime.strptime(stock.list_date[:10], "%Y-%m-%d").date()
                days_listed = (current_date - list_dt).days
                if days_listed < min_listing_days:
                    continue
            except (ValueError, TypeError):
                pass

        filtered.append(stock)

    return filtered
