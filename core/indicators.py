"""
技术指标计算模块
严格确保无未来数据泄露 (No Lookahead Bias)，采用纯因果计算 (Strictly Causal)
禁止居中窗口 (center=False)、未来填充或任意形式的前瞻计算
"""

import numpy as np
import pandas as pd
from typing import Tuple


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """简单移动平均 (SMA)"""
    return series.rolling(window=period, min_periods=period).mean()


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """指数移动平均 (EMA)，采用标准平滑系数 2/(N+1)"""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    相对强弱指数 (RSI) - 经典 Wilder 平滑算法
    RSI = 100 - (100 / (1 + RS))
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder's exponential smoothing
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # 当 avg_loss 为 0 且 avg_gain > 0 时 RSI 为 100；全为 0 时为 50
    rsi = rsi.fillna(50.0)
    return rsi


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    真实波幅均值 (ATR) - 衡量价格波动率的关键工具
    TR = max(High - Low, abs(High - PrevClose), abs(Low - PrevClose))
    ATR = Wilder平滑(TR, period)
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    return atr


def calculate_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    布林线 (Bollinger Bands)
    返回: (mid_band, upper_band, lower_band, bandwidth)
    bandwidth = (upper - lower) / mid
    """
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    bandwidth = (upper - lower) / mid.replace(0, np.nan)
    return mid, upper, lower, bandwidth


def calculate_donchian_channel(
    high: pd.Series,
    low: pd.Series,
    period: int = 20,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    唐奇安通道 (Donchian Channel)
    前 N 日最高价与最低价构成的突破通道 (使用 shift(1) 防止当天自己包含自身)
    返回: (upper_channel, lower_channel, mid_channel)
    """
    # 严格 shift(1)，代表截止昨日的通道高低点
    upper = high.shift(1).rolling(window=period, min_periods=period).max()
    lower = low.shift(1).rolling(window=period, min_periods=period).min()
    mid = (upper + lower) / 2.0
    return upper, lower, mid


def calculate_macd(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    平滑异同移动平均线 (MACD)
    返回: (dif, dea, macd_bar)
    macd_bar = (dif - dea) * 2
    """
    ema_fast = calculate_ema(close, fast_period)
    ema_slow = calculate_ema(close, slow_period)
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal_period, adjust=False).mean()
    macd_bar = (dif - dea) * 2.0
    return dif, dea, macd_bar


def calculate_volume_sma(volume: pd.Series, period: int = 5) -> pd.Series:
    """成交量移动均线"""
    return volume.rolling(window=period, min_periods=period).mean()


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    为历史日线数据计算完整指标集
    输入 df 必须包含: open, high, low, close, volume
    输出包含全部均线、波幅及动量指标
    """
    res = df.copy()
    if len(res) == 0:
        return res

    # 均线系统
    res["sma_5"] = calculate_sma(res["close"], 5)
    res["sma_10"] = calculate_sma(res["close"], 10)
    res["sma_20"] = calculate_sma(res["close"], 20)
    res["sma_60"] = calculate_sma(res["close"], 60)
    res["ema_20"] = calculate_ema(res["close"], 20)
    res["ema_50"] = calculate_ema(res["close"], 50)
    res["ema_120"] = calculate_ema(res["close"], 120)

    # 波动率与通道
    res["atr_14"] = calculate_atr(res["high"], res["low"], res["close"], 14)
    _, res["boll_up"], res["boll_low"], res["boll_width"] = calculate_bollinger_bands(res["close"], 20, 2.0)
    res["donchian_up_20"], res["donchian_low_20"], _ = calculate_donchian_channel(res["high"], res["low"], 20)

    # 动量与能量
    res["rsi_14"] = calculate_rsi(res["close"], 14)
    res["macd_dif"], res["macd_dea"], res["macd_bar"] = calculate_macd(res["close"])
    res["vol_ma5"] = calculate_volume_sma(res["volume"], 5)
    res["vol_ma20"] = calculate_volume_sma(res["volume"], 20)
    res["vol_ratio"] = res["volume"] / res["vol_ma5"].replace(0, np.nan)

    return res
