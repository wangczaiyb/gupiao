"""
回测引擎高精度规则与保守执行检验单元测试
"""

from typing import List
import numpy as np
import pandas as pd
import pytest

from core.backtest_engine import BacktestEngine
from core.strategies.base import BaseStrategy, SignalType, StrategySignal


class MockDeterministicStrategy(BaseStrategy):
    """用于精确检验回测执行逻辑的确定性模拟策略"""

    def __init__(self, buy_on_date: str, stop_loss: float, take_profit: float):
        super().__init__(name="MockDeterministicStrategy")
        self.buy_on_date = buy_on_date
        self.stop_loss = stop_loss
        self.take_profit = take_profit

    def get_description(self):
        return {}

    def evaluate_latest(self, df: pd.DataFrame, symbol: str) -> StrategySignal:
        cur_date = str(df["date"].iloc[-1])[:10]
        close = float(df["close"].iloc[-1])
        if cur_date == self.buy_on_date:
            return StrategySignal(
                symbol=symbol,
                date=cur_date,
                signal_type=SignalType.BUY,
                strategy_name=self.name,
                candidate_entry_price=close,
                stop_loss_price=self.stop_loss,
                take_profit_price=self.take_profit,
            )
        return StrategySignal(
            symbol=symbol,
            date=cur_date,
            signal_type=SignalType.NONE,
            strategy_name=self.name,
        )

    def generate_signals(self, df: pd.DataFrame, symbol: str) -> List[StrategySignal]:
        signals = []
        for i in range(len(df)):
            sub_df = df.iloc[: i + 1]
            sig = self.evaluate_latest(sub_df, symbol)
            if sig.is_actionable:
                signals.append(sig)
        return signals


def test_next_bar_open_execution_and_t_plus_one():
    """
    核心要求 1 & 3:
    1. 信号在 T 日 (2024-05-13) 收盘生成，必须在 T+1 日 (2024-05-14) 开盘按开盘价执行买入，禁止当日收盘偷价！
    2. T+1 日买入后，当天禁止卖出，最早在 T+2 日 (2024-05-15) 才能执行卖出！
    """
    df = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16"],
        "open": [10.0, 10.2, 10.8, 11.5],
        "high": [10.5, 10.4, 11.2, 11.6],
        "low": [9.8, 9.9, 10.7, 11.2],
        "close": [10.1, 10.3, 11.0, 11.5],
        "volume": [100000.0, 100000.0, 100000.0, 100000.0],
        "amount": [1000000.0, 1000000.0, 1000000.0, 1000000.0],
    })

    # 5月13日生成买入信号，止盈设为 10.9 (5月15日最高价11.2可触及)
    strat = MockDeterministicStrategy(buy_on_date="2024-05-13", stop_loss=9.0, take_profit=10.9)
    engine = BacktestEngine(initial_capital=100000.0, slippage_rate=0.0)

    metrics, equity_df, trades = engine.run_portfolio({"600519": df}, strat)

    assert len(trades) == 1
    t = trades[0]
    # 买入必须在 2024-05-14 开盘执行，价格为 10.2
    assert t.entry_date == "2024-05-14"
    assert t.entry_price == 10.2
    # 卖出在 2024-05-15 达到止盈 10.9 退出 (符合 T+1 可卖规定)
    assert t.exit_date == "2024-05-15"
    assert t.exit_price == 10.9
    assert t.exit_reason == "TAKE_PROFIT"


def test_conservative_same_bar_conflict_handling():
    """
    核心要求 4:
    同一根日 K (2024-05-15) 最低价 8.8 (触及止损 9.0)，最高价 12.0 (触及止盈 11.5)
    严格按保守逻辑：认定先触及止损，按止损平仓结算！
    """
    df = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15"],
        "open": [10.0, 10.0, 10.0],
        "high": [10.2, 10.2, 12.0],  # 触及止盈 11.5
        "low": [9.9, 9.9, 8.8],  # 触及止损 9.0
        "close": [10.1, 10.1, 10.5],
        "volume": [100000.0, 100000.0, 100000.0],
        "amount": [1000000.0, 1000000.0, 1000000.0],
    })

    strat = MockDeterministicStrategy(buy_on_date="2024-05-13", stop_loss=9.0, take_profit=11.5)
    engine = BacktestEngine(initial_capital=100000.0, slippage_rate=0.0)

    metrics, equity_df, trades = engine.run_portfolio({"600519": df}, strat)

    assert len(trades) == 1
    t = trades[0]
    assert t.is_conservative_conflict is True
    assert "Conservative" in t.exit_reason
    assert t.exit_price == 9.0  # 保守按止损结算，不能认定按11.5止盈！


def test_gap_down_stop_loss_execution_at_open():
    """
    核心要求 5:
    跳空低开跌破止损价时，不能假设总能在止损价退出，必须以开盘价成交！
    止损设定 9.0，次日开盘跳空低开至 8.5
    实际出场价格必须为 8.5，而不是 9.0！
    """
    df = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15"],
        "open": [10.0, 10.0, 8.5],  # 开盘直接跳空到 8.5 (低于止损 9.0)
        "high": [10.2, 10.2, 8.9],
        "low": [9.9, 9.9, 8.2],
        "close": [10.1, 10.1, 8.6],
        "volume": [100000.0, 100000.0, 100000.0],
        "amount": [1000000.0, 1000000.0, 1000000.0],
    })

    strat = MockDeterministicStrategy(buy_on_date="2024-05-13", stop_loss=9.0, take_profit=12.0)
    engine = BacktestEngine(initial_capital=100000.0, slippage_rate=0.0)

    metrics, equity_df, trades = engine.run_portfolio({"600519": df}, strat)

    assert len(trades) == 1
    t = trades[0]
    assert t.is_gap_exit is True
    assert t.exit_price == 8.5  # 必须以开盘价成交！


def test_empty_stock_pool_edge_case():
    """测试空股票池边界处理，不报错且返回标准零指标"""
    strat = MockDeterministicStrategy(buy_on_date="2024-05-13", stop_loss=9.0, take_profit=12.0)
    engine = BacktestEngine(initial_capital=100000.0)

    metrics, equity_df, trades = engine.run_portfolio({}, strat)
    assert metrics.total_trades == 0
    assert metrics.total_net_pnl == 0.0
    assert metrics.total_return_pct == 0.0
    assert len(trades) == 0


def test_limit_up_open_buy_restriction_in_backtest():
    """
    核心要求:
    若 T+1 日开盘直接一字涨停 (开盘价达到或超过涨停价 11.0)，
    买单无法成交，当日不得开仓！
    """
    df = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15"],
        "open": [10.0, 11.0, 11.5],  # 5月14日开盘价 11.0 触及前日收盘 10.0 的 10% 涨停！
        "high": [10.0, 11.0, 11.8],
        "low": [10.0, 11.0, 11.2],
        "close": [10.0, 11.0, 11.6],
        "prev_close": [10.0, 10.0, 11.0],
        "volume": [100000.0, 1000.0, 50000.0],
        "amount": [1000000.0, 11000.0, 575000.0],
    })

    strat = MockDeterministicStrategy(buy_on_date="2024-05-13", stop_loss=9.0, take_profit=15.0)
    engine = BacktestEngine(initial_capital=100000.0)

    metrics, equity_df, trades = engine.run_portfolio({"600519": df}, strat)

    # 因为 5月14日开盘涨停买不进，所以没有任何成交！
    assert len(trades) == 0


def test_multi_stock_shared_cash_pool_constraint():
    """
    核心要求 6:
    多股票组合必须共享同一个账户现金池，绝不能每只股票都使用全部本金后再叠加收益！
    本金 100,000 元，单票仓位上限 25% (25,000元)。
    同时有两个股票产生信号时，开完第一只股票后现金扣减，第二只股票只能使用剩余现金，总资产不得虚增。
    """
    df1 = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15"],
        "open": [10.0, 10.0, 11.0],
        "high": [10.2, 10.5, 11.5],
        "low": [9.8, 9.8, 10.8],
        "close": [10.0, 10.4, 11.2],
        "volume": [100000.0, 100000.0, 100000.0],
        "amount": [1000000.0, 1000000.0, 1000000.0],
    })
    df2 = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15"],
        "open": [20.0, 20.0, 22.0],
        "high": [20.4, 20.8, 22.5],
        "low": [19.6, 19.8, 21.6],
        "close": [20.0, 20.6, 22.2],
        "volume": [100000.0, 100000.0, 100000.0],
        "amount": [2000000.0, 2000000.0, 2000000.0],
    })

    strat = MockDeterministicStrategy(buy_on_date="2024-05-13", stop_loss=5.0, take_profit=30.0)
    engine = BacktestEngine(initial_capital=100000.0, risk_per_trade_pct=0.25, max_position_pct_per_stock=0.25)

    metrics, equity_df, trades = engine.run_portfolio({"600519": df1, "000001": df2}, strat)

    # 检查 5月14日当天账户现金状态
    row_14 = equity_df[equity_df["date"] == "2024-05-14"].iloc[0]
    # 两只标的各自占用约 25,000 元，总占用约 50,000 元，现金必须扣减到约 50,000 元，不能为负
    assert row_14["cash"] < 60000.0
    assert row_14["cash"] > 40000.0
    assert row_14["open_positions_count"] == 2


def test_backtest_reproducibility():
    """核心要求 13: 相同策略版本与数据，回测结果与指标 100% 可复现"""
    df = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16"],
        "open": [10.0, 10.2, 10.8, 11.5],
        "high": [10.5, 10.4, 11.2, 11.6],
        "low": [9.8, 9.9, 10.7, 11.2],
        "close": [10.1, 10.3, 11.0, 11.5],
        "volume": [100000.0, 100000.0, 100000.0, 100000.0],
        "amount": [1000000.0, 1000000.0, 1000000.0, 1000000.0],
    })
    strat = MockDeterministicStrategy(buy_on_date="2024-05-13", stop_loss=9.0, take_profit=10.9)
    engine = BacktestEngine(initial_capital=100000.0)

    m1, eq1, t1 = engine.run_portfolio({"600519": df}, strat)
    m2, eq2, t2 = engine.run_portfolio({"600519": df}, strat)

    assert m1.final_equity == m2.final_equity
    assert m1.total_return_pct == m2.total_return_pct
    assert len(t1) == len(t2)
    assert t1[0].net_pnl == t2[0].net_pnl


def test_backtest_st_and_ipo_price_limit_propagation():
    """测试回测引擎正确接收并应用 ST (5%涨停) 与无涨跌幅限制状态"""
    # 构造标的：主板股票，前收 10.00，次日开盘 10.50 (刚好涨 5.0%)
    # 若 is_st=True，则 10.50 属于一字涨停，必须被拦截禁止开盘买入！
    df_st = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14"],
        "open": [10.0, 10.50],
        "high": [10.0, 10.50],
        "low": [10.0, 10.50],
        "close": [10.0, 10.50],
        "prev_close": [10.0, 10.0],
        "is_st": [True, True],
        "volume": [10000.0, 10000.0],
        "amount": [100000.0, 105000.0],
    })
    strat = MockDeterministicStrategy(buy_on_date="2024-05-13", stop_loss=9.0, take_profit=11.5)
    engine = BacktestEngine(initial_capital=100000.0)

    # 运行回测：由于次日一字涨停 (5% 涨停限制)，买入应被限制拦截
    _, _, trades = engine.run_portfolio({"600000": df_st}, strat)
    assert len(trades) == 0  # 成功拦截，无法开盘买入


def test_backtest_cross_stock_signal_ranking_priority():
    """测试同日多标的买入信号按确定性/优先级排序，高分标的优先消耗资金与配额"""
    class ScoredMockStrategy(BaseStrategy):
        def __init__(self, scores: dict):
            super().__init__(name="ScoredMockStrategy")
            self.scores = scores

        def get_description(self): return {}

        def evaluate_latest(self, df: pd.DataFrame, symbol: str) -> StrategySignal:
            cur_date = str(df["date"].iloc[-1])[:10]
            close = float(df["close"].iloc[-1])
            return StrategySignal(
                symbol=symbol,
                date=cur_date,
                signal_type=SignalType.BUY,
                strategy_name=self.name,
                candidate_entry_price=close,
                stop_loss_price=close * 0.95,
                take_profit_price=close * 1.10,
                priority_score=self.scores.get(symbol, 0.0),
            )

        def generate_signals(self, df: pd.DataFrame, symbol: str) -> List[StrategySignal]:
            return [self.evaluate_latest(df.iloc[:1], symbol)]

    df1 = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15"],
        "open": [10.0, 10.0, 11.5], "high": [10.0, 10.5, 12.0], "low": [10.0, 9.8, 11.0], "close": [10.0, 10.2, 11.8],
        "volume": [10000.0, 10000.0, 10000.0], "amount": [100000.0, 100000.0, 118000.0],
    })
    df2 = pd.DataFrame({
        "date": ["2024-05-13", "2024-05-14", "2024-05-15"],
        "open": [20.0, 20.0, 23.0], "high": [20.0, 20.5, 24.0], "low": [20.0, 19.8, 22.5], "close": [20.0, 20.2, 23.5],
        "volume": [10000.0, 10000.0, 10000.0], "amount": [200000.0, 200000.0, 235000.0],
    })

    # 给 000001 打高分 95.0，给 600519 打低分 50.0
    strat = ScoredMockStrategy(scores={"600519": 50.0, "000001": 95.0})
    # 限制最大持仓标的数为 1 (只能买入得分更高的一只)
    engine = BacktestEngine(initial_capital=100000.0, max_concurrent_positions=1)

    m, eq, t = engine.run_portfolio({"600519": df1, "000001": df2}, strat)
    assert len(t) == 1
    # 验证实际入场并最终结算是高得分的 000001
    assert t[0].symbol == "000001"



