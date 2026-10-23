"""
波段交易策略逻辑与信号生成单元测试
"""

import numpy as np
import pandas as pd
from core.indicators import compute_all_indicators
from core.strategies.range_breakout import RangeBreakoutStrategy
from core.strategies.trend_pullback import TrendPullbackStrategy


def _create_uptrend_pullback_df():
    """构造一段典型的上升趋势后缩量回踩 EMA20 并放量企稳的形态"""
    dates = pd.date_range("2024-01-01", periods=160, freq="D").strftime("%Y-%m-%d")
    # 前 140 天稳步上涨
    p1 = np.linspace(10.0, 20.0, 140)
    # 第 141-155 天小幅回踩至 18.5
    p2 = np.linspace(20.0, 18.5, 15)
    # 第 156-160 天企稳收大阳线放量
    p3 = np.array([18.6, 18.8, 19.1, 19.4, 19.8])
    close = np.concatenate([p1, p2, p3])
    high = close + 0.3
    low = close - 0.3
    open_p = close - 0.1
    vol = np.full(160, 50000.0)
    vol[-1] = 90000.0  # 放量
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


def test_trend_pullback_evaluation():
    """测试趋势回调策略能够正确计算已满足与待满足条件，并给出客观止损"""
    df = _create_uptrend_pullback_df()
    strat = TrendPullbackStrategy()
    sig = strat.evaluate_latest(df, "600519")

    assert sig.symbol == "600519"
    assert sig.strategy_name == "趋势回调观察策略"
    assert sig.candidate_entry_price > 0
    assert sig.stop_loss_price < sig.candidate_entry_price
    assert "止损" in sig.stop_loss_rationale
    assert len(sig.risks) >= 2


def test_range_breakout_evaluation():
    """测试区间突破策略对箱体阻力突破的识别与止损设定"""
    dates = pd.date_range("2024-01-01", periods=100, freq="D").strftime("%Y-%m-%d")
    # 前 90 天在 10 ~ 11 元窄幅箱体横盘
    close = np.full(100, 10.5)
    close[:90] = 10.0 + (np.sin(np.linspace(0, 20, 90)) * 0.4)
    # 第 99 天强力放量突破到 12.0
    close[-1] = 12.0
    open_p = np.full(100, 10.4)
    open_p[-1] = 10.6
    high = np.maximum(close, open_p) + 0.2
    low = np.minimum(close, open_p) - 0.2
    vol = np.full(100, 20000.0)
    vol[-1] = 80000.0  # 倍量突破
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
    df = compute_all_indicators(df)

    strat = RangeBreakoutStrategy({"channel_period": 20})
    sig = strat.evaluate_latest(df, "000001")

    assert sig.candidate_entry_price > 0
    assert sig.stop_loss_price < sig.candidate_entry_price
    assert "突破" in sig.stop_loss_rationale


def test_trend_pullback_rejects_severe_breakdown_below_ema20():
    """测试当股价严重破位跌破 EMA20 时，策略必须正确识别为待满足/失效，不能因缺少负向约束误判为买入"""
    df = _create_uptrend_pullback_df()
    # 模拟最新一天的最低价和收盘价严重下砸破位，跌破 EMA20 达到 8%
    df_broken = df.copy()
    ema20_val = df_broken["ema_20"].iloc[-1]
    df_broken.loc[df_broken.index[-1], "low"] = ema20_val * 0.90  # 跌破 10%
    df_broken.loc[df_broken.index[-1], "close"] = ema20_val * 0.92

    strat = TrendPullbackStrategy({"pullback_margin": 0.02})
    sig = strat.evaluate_latest(df_broken, "600519")

    # 绝不能生成有效买入信号
    assert not sig.is_actionable
    # 待满足条件中必须指出跌破 EMA20 支撑
    assert any("跌破 EMA20" in cond for cond in sig.conditions_pending)

