"""
A 股交易日历模块
基于真实交易所（上交所/深交所/北交所）开市日历
禁止使用简单的“周一到周五”替代真实交易日，严谨处理春节、国庆、清明、五一、端午、中秋及元旦休市
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Set, Union


# 2020年至2026年中国A股休市日历集合 (法定节假日、调休不交易日及周末)
# 格式: 'YYYY-MM-DD'
A_SHARE_HOLIDAYS: Set[str] = {
    # 2020
    "2020-01-01", "2020-01-24", "2020-01-27", "2020-01-28", "2020-01-29", "2020-01-30", "2020-01-31",
    "2020-04-06", "2020-05-01", "2020-05-04", "2020-05-05", "2020-06-25", "2020-06-26",
    "2020-10-01", "2020-10-02", "2020-10-05", "2020-10-06", "2020-10-07", "2020-10-08",
    # 2021
    "2021-01-01", "2021-02-11", "2021-02-12", "2021-02-15", "2021-02-16", "2021-02-17",
    "2021-04-05", "2021-05-03", "2021-05-04", "2021-05-05", "2021-06-14", "2021-09-20", "2021-09-21",
    "2021-10-01", "2021-10-04", "2021-10-05", "2021-10-06", "2021-10-07",
    # 2022
    "2022-01-03", "2022-01-31", "2022-02-01", "2022-02-02", "2022-02-03", "2022-02-04",
    "2022-04-04", "2022-04-05", "2022-05-02", "2022-05-03", "2022-05-04", "2022-06-03",
    "2022-09-12", "2022-10-03", "2022-10-04", "2022-10-05", "2022-10-06", "2022-10-07",
    # 2023
    "2023-01-02", "2023-01-23", "2023-01-24", "2023-01-25", "2023-01-26", "2023-01-27",
    "2023-04-05", "2023-05-01", "2023-05-02", "2023-05-03", "2023-06-22", "2023-06-23",
    "2023-09-29", "2023-10-02", "2023-10-03", "2023-10-04", "2023-10-05", "2023-10-06",
    # 2024
    "2024-01-01", "2024-02-09", "2024-02-12", "2024-02-13", "2024-02-14", "2024-02-15", "2024-02-16",
    "2024-04-04", "2024-04-05", "2024-05-01", "2024-05-02", "2024-05-03", "2024-06-10",
    "2024-09-16", "2024-09-17", "2024-10-01", "2024-10-02", "2024-10-03", "2024-10-04", "2024-10-07",
    # 2025
    "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31", "2025-02-03", "2025-02-04",
    "2025-04-04", "2025-05-01", "2025-05-02", "2025-05-05", "2025-05-30", "2025-10-01", "2025-10-02",
    "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08",
    # 2026
    "2026-01-01", "2026-01-02", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-04-06", "2026-05-01", "2026-05-04", "2026-05-05", "2026-06-19", "2026-09-25",
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",
}


def to_date_obj(d: Union[str, date, datetime]) -> date:
    """转换为标准 date 对象"""
    if isinstance(d, str):
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    elif isinstance(d, datetime):
        return d.date()
    return d


def is_trading_day(d: Union[str, date, datetime], dynamic_calendar: Optional[Set[str]] = None) -> bool:
    """
    判断指定日期是否为 A 股交易日
    - 周六、周日休市
    - 法定节假日休市
    - 支持传入 dynamic_calendar (从行情接口实时加载的交易日清单)
    """
    target = to_date_obj(d)
    date_str = target.strftime("%Y-%m-%d")

    if dynamic_calendar is not None:
        return date_str in dynamic_calendar

    # 1. 检查是否为周末 (5: 周六, 6: 周日)
    if target.weekday() >= 5:
        return False

    # 2. 检查法定节假日
    if date_str in A_SHARE_HOLIDAYS:
        return False

    return True


def get_next_trading_day(
    d: Union[str, date, datetime],
    dynamic_calendar: Optional[Set[str]] = None,
    max_lookahead_days: int = 30,
) -> date:
    """
    获取指定日期的下一个交易日
    用于下一可交易时点执行 (Next Bar Execution)
    """
    current = to_date_obj(d) + timedelta(days=1)
    for _ in range(max_lookahead_days):
        if is_trading_day(current, dynamic_calendar):
            return current
        current += timedelta(days=1)
    return current


def get_t_plus_n_date(
    trade_date: Union[str, date, datetime],
    n: int = 1,
    dynamic_calendar: Optional[Set[str]] = None,
) -> date:
    """
    计算 T+N 交易日 (用于严格执行 T+1 卖出资格验证)
    """
    current = to_date_obj(trade_date)
    count = 0
    while count < n:
        current += timedelta(days=1)
        if is_trading_day(current, dynamic_calendar):
            count += 1
    return current


def get_trading_days_range(
    start_date: Union[str, date, datetime],
    end_date: Union[str, date, datetime],
    dynamic_calendar: Optional[Set[str]] = None,
) -> List[str]:
    """
    获取指定区间内的所有 A 股交易日列表 (升序排列)
    """
    start = to_date_obj(start_date)
    end = to_date_obj(end_date)
    cur = start
    days = []
    while cur <= end:
        if is_trading_day(cur, dynamic_calendar):
            days.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return days
