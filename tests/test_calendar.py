"""
A 股交易日历与 T+1 计算单元测试
"""

from datetime import date
from core.calendar import is_trading_day, get_next_trading_day, get_t_plus_n_date


def test_calendar_trading_days_and_holidays():
    """测试周末休市与法定节假日休市"""
    # 周末休市测试 (2024-05-18 是周六，2024-05-19 是周日)
    assert is_trading_day(date(2024, 5, 18)) is False
    assert is_trading_day(date(2024, 5, 19)) is False
    assert is_trading_day(date(2024, 5, 20)) is True  # 周一工作交易日

    # 国庆休市测试 (2024-10-01 至 2024-10-07)
    assert is_trading_day("2024-10-01") is False
    assert is_trading_day("2024-10-03") is False
    assert is_trading_day("2024-10-08") is True  # 节后第一个开市日


def test_next_trading_day_and_t_plus_one():
    """测试跨周末与跨假日的下一交易日及 T+1 卖出日"""
    # 2024-05-17 (周五) 买入，下一交易日与 T+1 均为 2024-05-20 (周一)
    assert get_next_trading_day(date(2024, 5, 17)) == date(2024, 5, 20)
    assert get_t_plus_n_date(date(2024, 5, 17), n=1) == date(2024, 5, 20)

    # 2024-09-30 (国庆假前最后一个交易日) 买入，T+1 为 2024-10-08
    assert get_t_plus_n_date(date(2024, 9, 30), n=1) == date(2024, 10, 8)
