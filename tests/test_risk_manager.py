"""
风险管理与仓位测算单元测试
"""

from core.risk_manager import RiskBudgetConfig, RiskManager


def test_position_sizing_fixed_risk_budget():
    """
    测试单笔固定风险百分比仓位算法
    总本金 100,000 元，单笔风险 1.5% (允许最大亏损 1,500 元)
    入场价 10.0 元，止损价 9.0 元 (每股风险 1.0 元)
    理论可买 = 1500 / 1.0 = 1500 股
    """
    config = RiskBudgetConfig(total_capital=100000.0, risk_per_trade_pct=0.015, max_single_stock_pct=0.25)
    rm = RiskManager(config)

    proposal = rm.calculate_position_size(
        symbol="600519",
        entry_price=10.0,
        stop_loss_price=9.0,
        current_cash=50000.0,
        current_positions={},
    )

    assert proposal.checks_passed is True
    # 主板 100 股整手规整
    assert proposal.recommended_shares == 1500
    assert proposal.recommended_amount == 15000.0
    # 占本金 15% (<= 25% 上限)
    assert proposal.position_pct_of_capital == 0.15


def test_position_sizing_single_stock_limit_cap():
    """测试单票持仓上限 (25%) 截断"""
    # 每股风险很小 (0.1元)，按风险算可买 15,000 股 (15万元，超总本金)
    config = RiskBudgetConfig(total_capital=100000.0, risk_per_trade_pct=0.015, max_single_stock_pct=0.25)
    rm = RiskManager(config)

    proposal = rm.calculate_position_size(
        symbol="600519",
        entry_price=10.0,
        stop_loss_price=9.9,
        current_cash=50000.0,
        current_positions={},
    )

    # 理论单票上限 25,000 元，按 10 元算最多 2500 股
    assert proposal.recommended_shares == 2500
    assert proposal.recommended_amount == 25000.0


def test_max_concurrent_positions_limit():
    """测试达到最大同时持仓数 (5只) 时禁止开仓"""
    config = RiskBudgetConfig(max_concurrent_positions=5)
    rm = RiskManager(config)

    existing_5 = {f"00000{i}": {"market_val": 10000, "industry": "科技"} for i in range(1, 6)}
    proposal = rm.calculate_position_size(
        symbol="600519",
        entry_price=10.0,
        stop_loss_price=9.0,
        current_cash=50000.0,
        current_positions=existing_5,
    )
    assert proposal.checks_passed is False
    assert any("持仓只数已达上限" in s for s in proposal.failed_checks)
