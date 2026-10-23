"""
V2 增量升级核心能力单元测试套件
覆盖:
1. 因子库与综合确定性评分 (AlphaSift 风格)
2. 相对强度动量策略与波动收缩突破策略 (VCP)
3. 真实小资金 (5000元) 整手约束与板块权限限制
4. 持仓体检引擎与组合集中度量化诊断
5. 可恢复批处理断点扫描任务调度器 (ResumableBatchScanner)
6. AKQuant 独立验证适配器平滑降级
"""

import numpy as np
import pandas as pd
import pytest

from core.akquant_adapter import AKQuantAdapter
from core.factors import compute_stock_factors
from core.indicators import compute_all_indicators
from core.portfolio_health import HoldingItem, PortfolioHealthAnalyzer
from core.risk_manager import RiskBudgetConfig, RiskManager
from core.strategies.rs_momentum import RSMomentumStrategy
from core.strategies.volatility_contraction import VolatilityContractionStrategy
from data_provider.batch_scanner import ResumableBatchScanner
from data_provider.manager import DataManager


def _create_sample_kline(n_bars: int = 100) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="D").strftime("%Y-%m-%d")
    close = np.linspace(10.0, 18.0, n_bars) + np.sin(np.linspace(0, 10, n_bars)) * 0.5
    high = close + 0.3
    low = close - 0.3
    open_p = close - 0.1
    vol = np.full(n_bars, 50000.0)
    vol[-1] = 120000.0
    amt = close * vol

    df = pd.DataFrame({
        "date": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": vol,
        "amount": amt,
    })
    return compute_all_indicators(df)


def test_factors_computation_and_certainty_score():
    """测试因子库正确计算各维度得分与确定性综合分"""
    df = _create_sample_kline(100)
    factors = compute_stock_factors(df, "600519")
    assert factors is not None
    assert 0.0 <= factors.trend_score <= 100.0
    assert 0.0 <= factors.momentum_score <= 100.0
    assert 0.0 <= factors.rs_score <= 100.0
    assert 0.0 <= factors.certainty_score <= 100.0

    # 测试样本不足时严谨返回 None，杜绝缺失值自动补成有利信号
    short_df = df.iloc[:30]
    assert compute_stock_factors(short_df, "600519") is None


def test_rs_momentum_and_vcp_strategies():
    """测试新增的相对强度动量策略与波动收缩突破策略"""
    df = _create_sample_kline(100)
    strat_rs = RSMomentumStrategy()
    sig_rs = strat_rs.evaluate_latest(df, "600519")
    assert sig_rs.strategy_name == "相对强度动量策略"
    assert sig_rs.candidate_entry_price > 0
    assert sig_rs.stop_loss_price < sig_rs.candidate_entry_price

    strat_vcp = VolatilityContractionStrategy()
    sig_vcp = strat_vcp.evaluate_latest(df, "300750")
    assert sig_vcp.strategy_name == "波动收缩突破策略"
    assert sig_vcp.candidate_entry_price > 0
    assert sig_vcp.stop_loss_price < sig_vcp.candidate_entry_price


def test_small_capital_and_board_permission_risk_control():
    """测试 5000 元真实小资金下的整手约束与板块权限拦截"""
    # 账户本金 5000 元，科创板权限未开通
    config = RiskBudgetConfig(
        total_capital=5000.0,
        user_permissions={"SH_MAIN": True, "SZ_MAIN": True, "CHINEXT": True, "STAR": False, "BSE": False},
    )
    rm = RiskManager(config)

    # 1. 科创板标的 (688981): 权限未开通拦截
    proposal_star = rm.calculate_position_size(
        symbol="688981", entry_price=50.0, stop_loss_price=47.0, current_cash=5000.0, current_positions={}
    )
    assert not proposal_star.checks_passed
    assert any("未勾选开通 [科创板] 交易权限" in msg for msg in proposal_star.failed_checks)

    # 2. 贵州茅台 (600519): 现价 1600 元，最低申报 100 股需 16 万元，5000 元小资金应触发整手资金不足诊断
    proposal_moutai = rm.calculate_position_size(
        symbol="600519", entry_price=1600.0, stop_loss_price=1500.0, current_cash=5000.0, current_positions={}
    )
    assert not proposal_moutai.checks_passed
    assert any("整手资金不足" in msg for msg in proposal_moutai.failed_checks)


def test_portfolio_health_analyzer():
    """测试持仓体检引擎输出结构化诊断与集中度警报"""
    dm = DataManager(db_path="data/test_stock.db", cache_dir="data/test_cache")
    analyzer = PortfolioHealthAnalyzer(dm)

    holdings = [
        HoldingItem(symbol="600519", cost_price=1700.0, shares=100),
        HoldingItem(symbol="000001", cost_price=10.0, shares=1000),
    ]
    summary = analyzer.analyze_portfolio(holdings)
    assert summary.positions_count == 2
    assert summary.total_cost > 0
    assert 0.0 <= summary.overall_health_score <= 100.0
    assert len(summary.detailed_positions) == 2


def test_resumable_batch_scanner_checkpointing(tmp_path):
    """测试批处理扫描任务断点续扫与进度持久化"""
    db_file = str(tmp_path / "test_tasks.db")
    scanner = ResumableBatchScanner(db_path=db_file)

    symbols = ["600519", "000001", "300750", "688981"]
    task = scanner.create_task("task_001", scope="TEST", strategy_name="Demo", symbols=symbols)
    assert task.total_symbols == 4
    assert task.processed_count == 0

    # 执行一个单步批次 (batch_size=2)
    def dummy_process(sym):
        return {"symbol": sym, "passed": True}

    status, is_done = scanner.run_step("task_001", dummy_process, batch_size=2)
    assert status.processed_count == 2
    assert status.last_symbol == "000001"
    assert not is_done

    # 再次推进批次，直至全部完成
    status_final, is_done_final = scanner.run_step("task_001", dummy_process, batch_size=5)
    assert status_final.processed_count == 4
    assert is_done_final
    assert status_final.status == "COMPLETED"


def test_akquant_adapter_graceful_fallback():
    """测试 AKQuant 未安装时的平滑状态降级"""
    adapter = AKQuantAdapter()
    res = adapter.validate_backtest({})
    assert res is not None
    assert isinstance(res.status_message, str)
