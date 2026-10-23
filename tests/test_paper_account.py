"""
模拟交易账户与记账生命周期单元测试
"""

import os
import pytest
from core.paper_account import OrderDirection, OrderStatus, PaperAccountManager


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_paper_account.db")


def test_paper_account_order_flow_and_t_plus_one(temp_db_path):
    """测试模拟买入、扣款、T+1锁定、平仓与现金回款记账一致性"""
    pm = PaperAccountManager(db_path=temp_db_path, initial_capital=50000.0)

    # 1. 初始状态检验
    summary = pm.get_account_summary()
    assert summary["initial_capital"] == 50000.0
    assert summary["cash"] == 50000.0
    assert summary["positions_count"] == 0

    # 2. 买入 100 股 600519，价格 100.0 元 (市值 10,000 元)
    order_buy = pm.place_order(
        symbol="600519",
        direction=OrderDirection.BUY,
        shares=100,
        price=100.0,
        reason="测试买入",
    )
    assert order_buy.status == OrderStatus.FILLED.value
    assert order_buy.filled_shares == 100
    assert order_buy.fee > 0

    # 检查现金扣减与持仓 (当日买入股份处于 T+1 锁定，可用可卖为 0)
    summary_after_buy = pm.get_account_summary({"600519": 100.0})
    assert summary_after_buy["cash"] < 40000.0  # 扣除了10000元及手续费
    assert summary_after_buy["positions_count"] == 1
    pos = summary_after_buy["positions"][0]
    assert pos.shares == 100
    assert pos.available_shares == 0  # 当日 T+0 不可卖！

    # 3. 尝试当日违规卖出：必须被拦截并标记为 UNFILLED
    order_illegal_sell = pm.place_order(
        symbol="600519",
        direction=OrderDirection.SELL,
        shares=100,
        price=105.0,
        reason="当日违规卖出尝试",
    )
    assert order_illegal_sell.status == OrderStatus.UNFILLED.value
    assert "T+1 可卖股数不足" in order_illegal_sell.reason

    # 4. 模拟次日 T+1 解锁可用额度并正常平仓卖出
    with pm._get_connection() as conn:
        conn.cursor().execute("UPDATE positions SET available_shares = 100 WHERE symbol = '600519'")
        conn.commit()

    order_sell = pm.place_order(
        symbol="600519",
        direction=OrderDirection.SELL,
        shares=100,
        price=110.0,  # 盈利 10 元/股
        reason="达到目标位止盈卖出",
    )
    assert order_sell.status == OrderStatus.FILLED.value

    summary_final = pm.get_account_summary()
    assert summary_final["positions_count"] == 0  # 仓位清空
    # 净现金必须大于初始 50000 元 (扣除了双边规费后的净利润)
    assert summary_final["cash"] > 50000.0


def test_insufficient_cash_order_rejection(temp_db_path):
    """测试可用现金不足时委托被拒绝 (UNFILLED)"""
    pm = PaperAccountManager(db_path=temp_db_path, initial_capital=5000.0)

    # 尝试买入 100 股茅台 (需要约 13 万元，远超 5000 元现金)
    order = pm.place_order(
        symbol="600519",
        direction=OrderDirection.BUY,
        shares=100,
        price=1300.0,
    )
    assert order.status == OrderStatus.UNFILLED.value
    assert "可用现金不足" in order.reason
