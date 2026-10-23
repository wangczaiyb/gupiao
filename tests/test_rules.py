"""
A 股交易规则、费率及板块申报机制单元测试
"""

from datetime import date
import pytest
from core.rules import (
    classify_symbol,
    get_board_rules,
    round_trade_quantity,
    get_stamp_tax_rate,
    get_transfer_fee_rate,
    calculate_trade_cost,
    calculate_price_limits,
    is_trade_restricted,
)


def test_board_classification():
    """测试五大板块精确分类"""
    assert classify_symbol("600519") == ("SH_MAIN", "SH", "沪市主板")
    assert classify_symbol("sh601318") == ("SH_MAIN", "SH", "沪市主板")
    assert classify_symbol("000001") == ("SZ_MAIN", "SZ", "深市主板")
    assert classify_symbol("002594.SZ") == ("SZ_MAIN", "SZ", "深市主板")
    assert classify_symbol("300750") == ("CHINEXT", "SZ", "创业板")
    assert classify_symbol("688981") == ("STAR", "SH", "科创板")
    assert classify_symbol("920211") == ("BSE", "BJ", "北交所")
    assert classify_symbol("832023") == ("BSE", "BJ", "北交所")
    assert classify_symbol("871642") == ("BSE", "BJ", "北交所")
    assert classify_symbol("430047") == ("BSE", "BJ", "北交所")


def test_lot_size_rounding():
    """测试不同板块买入与卖出申报数量规则"""
    # 主板: 100股为一手，整手递增
    assert round_trade_quantity(99, "600519", is_buy=True) == 0
    assert round_trade_quantity(150, "600519", is_buy=True) == 100
    assert round_trade_quantity(299, "000001", is_buy=True) == 200

    # 科创板: 起报200股，超过部分可以1股递增
    assert round_trade_quantity(199, "688981", is_buy=True) == 0
    assert round_trade_quantity(200, "688981", is_buy=True) == 200
    assert round_trade_quantity(205, "688981", is_buy=True) == 205

    # 北交所: 起报100股，超过部分可以1股递增
    assert round_trade_quantity(99, "920211", is_buy=True) == 0
    assert round_trade_quantity(100, "920211", is_buy=True) == 100
    assert round_trade_quantity(107, "920211", is_buy=True) == 107

    # 卖出: 允许零股卖出
    assert round_trade_quantity(53, "600519", is_buy=False) == 53


def test_stamp_tax_effective_date():
    """测试印花税减半政策生效日切换 (2023-08-28)"""
    # 2023-08-27 及以前: 0.1%
    assert get_stamp_tax_rate(date(2023, 8, 25)) == 0.0010
    # 2023-08-28 起: 0.05%
    assert get_stamp_tax_rate(date(2023, 8, 28)) == 0.0005
    assert get_stamp_tax_rate(date(2024, 1, 1)) == 0.0005


def test_transfer_fee_effective_date():
    """测试中国结算过户费减半生效日切换 (2022-04-29)"""
    # 2022-04-28 及以前: 0.02‰ (0.00002)
    assert get_transfer_fee_rate(date(2022, 4, 28)) == 0.00002
    # 2022-04-29 起: 0.01‰ (0.00001)
    assert get_transfer_fee_rate(date(2022, 4, 29)) == 0.00001


def test_min_commission_and_fees():
    """测试佣金最低5元限制与印花税单边征收"""
    # 买入 1000 元，按万2.5佣金为 0.25 元，触发最低 5 元
    buy_fee = calculate_trade_cost(1000.0, is_buy=True, commission_rate=0.00025, min_commission=5.0)
    assert buy_fee.min_commission_applied is True
    assert buy_fee.commission == 5.0
    assert buy_fee.stamp_tax == 0.0  # 买入免印花税

    # 卖出 100,000 元 (在2024年)
    sell_fee = calculate_trade_cost(100000.0, is_buy=False, trade_date=date(2024, 5, 1), commission_rate=0.00025)
    assert sell_fee.commission == 25.0
    assert sell_fee.stamp_tax == 50.0  # 10万 * 0.05% = 50元
    assert sell_fee.transfer_fee == 1.0  # 10万 * 0.01‰ = 1元
    assert sell_fee.total_fee == 76.0


def test_price_limits_and_restrictions():
    """测试主板/创业板/科创板/北交所/ST股票涨跌停价计算与交易限制"""
    # 主板: 10%
    up, down = calculate_price_limits(10.0, "600519")
    assert up == 11.00
    assert down == 9.00

    # 创业板: 20%
    up, down = calculate_price_limits(100.0, "300750")
    assert up == 120.00
    assert down == 80.00

    # 北交所: 30%
    up, down = calculate_price_limits(20.0, "920211")
    assert up == 26.00
    assert down == 14.00

    # 主板 ST 股票: 5%
    up, down = calculate_price_limits(10.0, "600000", is_st=True)
    assert up == 10.50
    assert down == 9.50

    # 一字涨停无法买入
    restricted, msg = is_trade_restricted(11.0, 11.0, 9.0, is_buy=True)
    assert restricted is True
    assert "封死无法买入" in msg

    # 一字跌停无法卖出
    restricted, msg = is_trade_restricted(9.0, 11.0, 9.0, is_buy=False)
    assert restricted is True
    assert "封死无法平仓" in msg

    # 停牌限制
    restricted, msg = is_trade_restricted(10.0, 11.0, 9.0, is_buy=True, is_suspended=True)
    assert restricted is True
    assert "停牌" in msg
