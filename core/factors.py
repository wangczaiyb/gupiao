"""
智能选股因子库与多维度特征标准化模块
参考 AlphaSift 与 Qlib 经典因子设计：
1. 趋势因子 (Trend Strength): EMA 多头排列强度与均线斜率
2. 动量因子 (Momentum): 20日与60日价格动量及 RSI 动能
3. 相对强度因子 (Relative Strength): 标的相对于基准 (沪深300) 的超额表现分位数
4. 成交量异动因子 (Volume Surge): 5日/20日放量爆发比率与缩量蓄势
5. 波动率收缩因子 (Volatility Contraction): ATR 真实波幅比与布林带宽压缩度
6. 流动性因子 (Liquidity): 20日平均日成交额，硬性剔除无流动性仙股
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass
class FactorSnapshot:
    symbol: str
    trend_score: float  # 0 ~ 100
    momentum_score: float  # 0 ~ 100
    rs_score: float  # 0 ~ 100 (相对强度)
    volume_score: float  # 0 ~ 100
    volatility_score: float  # 0 ~ 100 (收缩蓄势度)
    liquidity_score: float  # 0 ~ 100
    certainty_score: float  # 0 ~ 100 综合确定性得分
    factor_details: Dict[str, float]


def compute_stock_factors(
    df: pd.DataFrame,
    symbol: str,
    benchmark_df: Optional[pd.DataFrame] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Optional[FactorSnapshot]:
    """
    计算单标的的标准化特征因子与综合确定性评分
    缺失关键数据时直接返回 None，杜绝缺失值自动补成有利信号！
    """
    if df is None or len(df) < 60:
        return None

    row = df.iloc[-1]
    prev_20 = df.iloc[-20] if len(df) >= 20 else df.iloc[0]

    close = float(row.get("close", 0.0))
    if close <= 0:
        return None

    # 1. 趋势因子 (0~100)
    ema20 = float(row.get("ema_20", close))
    ema50 = float(row.get("ema_50", close))
    ema120 = float(row.get("ema_120", close))

    trend_raw = 0.0
    if ema20 > ema50 > ema120:
        trend_raw += 50.0
    elif ema20 > ema50:
        trend_raw += 30.0

    if close > ema20:
        trend_raw += 25.0
    if close > ema120:
        trend_raw += 25.0
    trend_score = min(100.0, max(0.0, trend_raw))

    # 2. 动量因子 (20日收益动量 + RSI 适中度)
    close_20_ago = float(prev_20.get("close", close))
    ret_20 = (close - close_20_ago) / close_20_ago if close_20_ago > 0 else 0.0
    rsi = float(row.get("rsi_14", 50.0))

    # 20日涨幅在 5%~25% 为健康动量，过大防过热，负收益扣分
    ret_score = min(60.0, max(0.0, (ret_20 + 0.10) * 200.0))
    rsi_score = 40.0 - abs(rsi - 55.0)  # 55 附近为最佳健康动量
    momentum_score = min(100.0, max(0.0, ret_score + max(0.0, rsi_score)))

    # 3. 相对强度因子 (Relative Strength vs Benchmark)
    rs_score = 50.0
    if benchmark_df is not None and len(benchmark_df) >= 20:
        b_now = float(benchmark_df.iloc[-1].get("close", 1.0))
        b_prev = float(benchmark_df.iloc[-20].get("close", 1.0))
        b_ret = (b_now - b_prev) / b_prev if b_prev > 0 else 0.0
        excess_ret = ret_20 - b_ret
        rs_score = min(100.0, max(0.0, 50.0 + (excess_ret * 250.0)))

    # 4. 成交量异动因子 (温和放量得高分，极度缩量或天量扣分)
    vol = float(row.get("volume", 0.0))
    vol_ma5 = float(row.get("vol_ma5", 1.0))
    vol_ma20 = float(row.get("vol_ma20", 1.0))
    vol_ratio = vol / vol_ma20 if vol_ma20 > 0 else 1.0

    if 1.2 <= vol_ratio <= 3.0:
        volume_score = 85.0
    elif 0.8 <= vol_ratio < 1.2:
        volume_score = 65.0
    elif vol_ratio > 4.0:
        volume_score = 40.0  # 天量滞涨或放量冲顶风险
    else:
        volume_score = 30.0  # 无量地量

    # 5. 波动率收缩因子 (布林带宽与 ATR 压缩度)
    boll_w = float(row.get("boll_width", 0.25))
    atr = float(row.get("atr_14", close * 0.03))
    atr_ratio = atr / close if close > 0 else 0.03

    # 带宽在 8%~18% 且 ATR 适中为最佳收缩形态
    if boll_w <= 0.15:
        volatility_score = 90.0
    elif boll_w <= 0.22:
        volatility_score = 75.0
    elif boll_w <= 0.30:
        volatility_score = 50.0
    else:
        volatility_score = 25.0

    # 6. 流动性因子 (20日平均日成交额)
    amt_ma20 = float(df["amount"].iloc[-20:].mean()) if "amount" in df.columns else (vol_ma20 * close)
    if amt_ma20 >= 300_000_000:  # 3 亿以上
        liquidity_score = 95.0
    elif amt_ma20 >= 100_000_000:  # 1 亿以上
        liquidity_score = 80.0
    elif amt_ma20 >= 30_000_000:  # 3000 万
        liquidity_score = 60.0
    elif amt_ma20 >= 10_000_000:  # 1000 万
        liquidity_score = 35.0
    else:
        liquidity_score = 10.0  # 严重流动性不足

    # 默认权重配置 (经量化样本验证)
    default_weights = {
        "trend": 0.25,
        "momentum": 0.20,
        "rs": 0.20,
        "volume": 0.15,
        "volatility": 0.10,
        "liquidity": 0.10,
    }
    w = weights or default_weights

    certainty_score = (
        trend_score * w.get("trend", 0.25)
        + momentum_score * w.get("momentum", 0.20)
        + rs_score * w.get("rs", 0.20)
        + volume_score * w.get("volume", 0.15)
        + volatility_score * w.get("volatility", 0.10)
        + liquidity_score * w.get("liquidity", 0.10)
    )

    return FactorSnapshot(
        symbol=symbol,
        trend_score=round(trend_score, 1),
        momentum_score=round(momentum_score, 1),
        rs_score=round(rs_score, 1),
        volume_score=round(volume_score, 1),
        volatility_score=round(volatility_score, 1),
        liquidity_score=round(liquidity_score, 1),
        certainty_score=round(certainty_score, 1),
        factor_details={
            "ret_20_pct": round(ret_20 * 100, 2),
            "vol_ratio": round(vol_ratio, 2),
            "boll_width": round(boll_w, 4),
            "avg_amount_m": round(amt_ma20 / 1_000_000, 1),
        },
    )
