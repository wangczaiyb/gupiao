"""
趋势回调观察策略 (Trend Pullback Strategy)
适用风格: 持有几天到几周的顺势波段交易
核心理念: “只在上升趋势中寻找低吸机会，不在下跌趋势中抄底”
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from core.strategies.base import BaseStrategy, SignalType, StrategySignal


class TrendPullbackStrategy(BaseStrategy):
    """
    趋势中的回调观察策略
    默认参数提供研究基准起点，参数完全支持在界面与回测中自由调整
    """

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        default_params = {
            "ema_fast": 20,  # 快速均线
            "ema_mid": 50,  # 中期趋势均线
            "ema_slow": 120,  # 长期多空基准均线
            "rsi_period": 14,  # RSI周期
            "rsi_min": 38.0,  # 回调吸纳 RSI 下限
            "rsi_max": 58.0,  # 回调吸纳 RSI 上限
            "pullback_margin": 0.02,  # 允许距离均线的误差幅度 (2%)
            "vol_factor": 1.05,  # 确认企稳时的放量系数 (较5日均量)
            "risk_reward_ratio": 2.5,  # 目标盈亏比
            "atr_multiplier": 1.2,  # 止损 ATR 乘数
        }
        if params:
            default_params.update(params)
        super().__init__(name="趋势回调观察策略", params=default_params)

    def get_description(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": "1.0.0",
            "concept": "在大级别均线维持多头排列的上升趋势中，等待股价回踩支撑位、RSI 指标消化超买后，捕捉缩量回踩后的企稳放量阳线入场。",
            "entry_conditions": [
                f"均线多头趋势：EMA({self.params['ema_fast']}) > EMA({self.params['ema_mid']}) > EMA({self.params['ema_slow']})，且收盘价运行在 EMA({self.params['ema_slow']}) 之上",
                f"回踩支撑区间：最低价曾回踩至 EMA({self.params['ema_fast']}) 附近（±{self.params['pullback_margin']*100:.1f}%）或在 EMA({self.params['ema_mid']}) 上方蓄势",
                f"动量指标重置：RSI({self.params['rsi_period']}) 处于 {self.params['rsi_min']} ~ {self.params['rsi_max']} 区间，表明前期过热已有效释放，尚未跌入极弱区",
                f"企稳确认阳线：当日收阳 (Close > Open)，且收盘价站上 5 日均线或突破昨日高点",
                f"成交量回暖：成交量达到 5 日均量的 {self.params['vol_factor']:.2f} 倍以上，呈现企稳放量态势",
            ],
            "exit_conditions": [
                "止损退出：收盘价跌破止损参考价 (近期波段低点 - 1.2 * ATR)",
                "跟踪止盈：达到目标盈亏比 (默认 2.5 倍风险距离) 后分批止盈，或当股价连续2日跌破 20日均线时出场",
                "失效条件：若买入后3个交易日内未能创出新高且有效跌破 EMA(50)，说明假突破企稳，立即主动离场",
            ],
            "parameters": self.params,
        }

    def evaluate_latest(self, df: pd.DataFrame, symbol: str) -> StrategySignal:
        """评估最新一根日 K 线的具体满足情况"""
        min_bars = max(self.params["ema_slow"], 60) + 10
        if len(df) < min_bars:
            return StrategySignal(
                symbol=symbol,
                date=df["date"].iloc[-1] if len(df) > 0 and "date" in df else "",
                signal_type=SignalType.NONE,
                strategy_name=self.name,
                conditions_pending=[f"数据不足，至少需要 {min_bars} 根历史日线数据计算 EMA({self.params['ema_slow']})"],
                risks=["样本历史过短，指标处于初始化不稳定阶段"],
            )

        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        date_str = str(row["date"])[:10]

        ema_f = row.get("ema_20", 0.0)
        ema_m = row.get("ema_50", 0.0)
        ema_s = row.get("ema_120", 0.0)
        close = row.get("close", 0.0)
        open_p = row.get("open", 0.0)
        low = row.get("low", 0.0)
        rsi = row.get("rsi_14", 50.0)
        vol = row.get("volume", 0.0)
        vol_ma5 = row.get("vol_ma5", 1.0)
        atr = row.get("atr_14", close * 0.03)

        conditions_met = []
        conditions_pending = []
        risks = []

        # 条件 1: 趋势多头
        trend_ok = (ema_f > ema_m > ema_s) and (close > ema_s)
        if trend_ok:
            conditions_met.append(f"均线多头结构良好 (EMA20={ema_f:.2f} > EMA50={ema_m:.2f} > EMA120={ema_s:.2f})")
        else:
            conditions_pending.append(f"等待均线形成多头排列 (当前 EMA20={ema_f:.2f}, EMA50={ema_m:.2f}, EMA120={ema_s:.2f})")

        # 条件 2: 回踩支撑 (增加负向边界约束，防止深度破位暴跌被错误识别为回踩)
        dist_to_ema20 = (low - ema_f) / ema_f if ema_f > 0 else 0.0
        margin = self.params["pullback_margin"]
        pullback_ok = (-margin <= dist_to_ema20 <= margin) and close >= (ema_m * 0.98)
        if pullback_ok:
            conditions_met.append(f"价格完成回踩支撑 (回踩至 EMA20 距离 {dist_to_ema20*100:.1f}%)")
        else:
            if dist_to_ema20 < -margin:
                conditions_pending.append(
                    f"价格跌破 EMA20 支撑位 (偏离度 {dist_to_ema20*100:.1f}% < 允许容忍下限 -{margin*100:.1f}%)，需等待重新站稳"
                )
            else:
                conditions_pending.append(
                    f"价格尚未回踩至支撑位附近 (当前偏离 EMA20 +{dist_to_ema20*100:.1f}%，目标 ≤ +{margin*100:.1f}%)"
                )

        # 条件 3: RSI 动量重置
        rsi_ok = self.params["rsi_min"] <= rsi <= self.params["rsi_max"]
        if rsi_ok:
            conditions_met.append(f"RSI 处于适度回调修复区 (RSI={rsi:.1f})")
        else:
            if rsi < self.params["rsi_min"]:
                conditions_pending.append(f"RSI 偏弱 (当前 RSI={rsi:.1f} < {self.params['rsi_min']})，需等待企稳不破位")
            else:
                conditions_pending.append(f"RSI 仍处于高位超买未充分消化 (当前 RSI={rsi:.1f} > {self.params['rsi_max']})")

        # 条件 4: 企稳阳线
        candle_ok = (close > open_p) and (close >= prev_row.get("high", close) * 0.995 or close > row.get("sma_5", close))
        if candle_ok:
            conditions_met.append(f"收出企稳阳线 (收盘={close:.2f}，开盘={open_p:.2f})")
        else:
            conditions_pending.append("尚未收出企稳反转阳线 (当日收阴或未突破短期均线)")

        # 条件 5: 成交量确认
        vol_threshold = vol_ma5 * self.params["vol_factor"]
        vol_ok = vol >= vol_threshold
        if vol_ok:
            conditions_met.append(f"企稳伴随温和放量 (成交量 {vol/100:.0f}手 ≥ 5日均量 {vol_ma5/100:.0f}手的 {self.params['vol_factor']:.2f}倍)")
        else:
            conditions_pending.append(f"成交量不足以确认企稳 (当日 {vol/100:.0f}手，待放量至 {vol_threshold/100:.0f}手)")

        # 计算止损与止盈
        # 止损：以近期5日最低点减去 ATR 乘数
        recent_low = df["low"].iloc[-5:].min()
        stop_dist = max(atr * self.params["atr_multiplier"], close * 0.03)
        stop_loss_price = round(min(recent_low - (atr * 0.5), close - stop_dist), 2)
        take_profit_price = round(close + (close - stop_loss_price) * self.params["risk_reward_ratio"], 2)

        stop_loss_rationale = (
            f"以近期波段低点 {recent_low:.2f} 下方缓冲 0.5*ATR 及当前收盘价下方 {self.params['atr_multiplier']} 倍 ATR "
            f"({stop_dist:.2f} 元) 计算止损位，防止洗盘"
        )

        # 风险揭示
        risks.append("若大盘或所属行业板块整体破位，个股回踩均线可能会演化为破位阴跌")
        if (close - stop_loss_price) / close > 0.08:
            risks.append(f"当前止损距离较宽 ({(close - stop_loss_price)/close*100:.1f}%)，建议严格控制仓位以防单笔风险超标")
        risks.append("跳空风险：遇到突发重大利空低开跌破止损价时，实际退出价格将低于预设止损价")

        signal_type = SignalType.BUY if len(conditions_pending) == 0 else SignalType.NONE

        return StrategySignal(
            symbol=symbol,
            date=date_str,
            signal_type=signal_type,
            strategy_name=self.name,
            candidate_entry_price=round(close, 2),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            stop_loss_rationale=stop_loss_rationale,
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            risks=risks,
            metrics={
                "close": close,
                "ema_20": ema_f,
                "ema_50": ema_m,
                "ema_120": ema_s,
                "rsi_14": rsi,
                "atr_14": atr,
                "vol_ratio": round(vol / vol_ma5, 2) if vol_ma5 > 0 else 1.0,
            },
        )

    def generate_signals(self, df: pd.DataFrame, symbol: str) -> List[StrategySignal]:
        """批量生成历史信号序列"""
        signals = []
        min_bars = max(self.params["ema_slow"], 60) + 10
        if len(df) < min_bars:
            return signals

        for i in range(min_bars, len(df)):
            sub_df = df.iloc[: i + 1]
            sig = self.evaluate_latest(sub_df, symbol)
            if sig.is_actionable:
                signals.append(sig)

        return signals
