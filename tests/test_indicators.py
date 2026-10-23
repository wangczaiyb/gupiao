"""
技术指标计算与无未来数据泄露 (Causality & No Lookahead Bias) 单元测试
"""

import numpy as np
import pandas as pd
import pytest
from core.indicators import (
    calculate_sma,
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    calculate_donchian_channel,
    compute_all_indicators,
)


def _generate_synthetic_kline(n_bars: int = 100) -> pd.DataFrame:
    """生成确定性的测试 K 线序列"""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="D").strftime("%Y-%m-%d")
    close = 10.0 + np.cumsum(np.random.randn(n_bars) * 0.2)
    high = close + np.random.rand(n_bars) * 0.3
    low = close - np.random.rand(n_bars) * 0.3
    open_p = (high + low) / 2.0
    vol = np.random.randint(1000, 50000, n_bars) * 100.0
    amt = close * vol
    return pd.DataFrame({
        "date": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": vol,
        "amount": amt,
    })


def test_indicators_strict_causality_no_future_leak():
    """
    核心要求: 指标在未来数据改变或追加时，过去的计算结果必须保持 100% 不变！
    """
    df_long = _generate_synthetic_kline(120)
    df_short = df_long.iloc[:80].copy()  # 前80根与 df_long 完全相同，模拟时间往后推移40天追加新K线

    ind_short = compute_all_indicators(df_short)
    ind_long = compute_all_indicators(df_long)

    # 校验前 80 根的指标数值必须完全相等 (允许微小的浮点精度误差)
    for col in ["sma_5", "sma_20", "ema_20", "ema_50", "rsi_14", "atr_14", "donchian_up_20"]:
        short_vals = ind_short[col].dropna()
        long_vals = ind_long[col].iloc[: len(ind_short)].dropna()
        np.testing.assert_allclose(
            short_vals.values,
            long_vals.values,
            rtol=1e-5,
            err_msg=f"指标 {col} 存在未来数据泄露！未来数据改变影响了过去计算结果！",
        )


def test_rsi_bounds_and_properties():
    """测试 RSI 取值范围始终位于 [0, 100] 之间"""
    df = _generate_synthetic_kline(60)
    rsi = calculate_rsi(df["close"], 14)
    valid_rsi = rsi.dropna()
    assert (valid_rsi >= 0.0).all()
    assert (valid_rsi <= 100.0).all()


def test_donchian_channel_lag():
    """测试唐奇安通道使用 shift(1)，当日最高价不会包含进入昨日形成的通道线中"""
    df = _generate_synthetic_kline(40)
    up, low, _ = calculate_donchian_channel(df["high"], df["low"], 20)
    # 第 25 天的唐奇安上轨必须等于前 20 天 (第 5 天到第 24 天) 的最高价
    expected_up_25 = df["high"].iloc[5:25].max()
    assert round(up.iloc[25], 4) == round(expected_up_25, 4)
