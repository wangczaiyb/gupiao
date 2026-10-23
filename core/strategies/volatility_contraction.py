"""
波动收缩突破策略 (Volatility Contraction Pattern - VCP)
适用风格: 捕捉主力高度控盘蓄势后、筹码锁定并在极窄波动后爆发的波段机会
核心理念: “波动率由大变小递减收敛，量能由喧嚣归于平静，随后以放量阳线穿透阻力突破”
"""

from typing import Any, Dict, List, Optional
import pandas as pd
from core.factors import compute_stock_factors
from core.strategies.base import BaseStrategy, SignalType, StrategySignal


class VolatilityContractionStrategy(BaseStrategy):
    """波动收缩突破观察策略 (VCP)"""

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        default_params = {
            "max_bandwidth": 0.16,  # 布林带宽压缩上限 (≤ 16%)
            "vol_breakout_mult": 1.5,  # 突破放量倍数 (较20日均量)
            "atr_multiplier": 1.2,  # 止损 ATR 乘数
            "risk_reward_ratio": 2.5,  # 目标盈亏比
        }
        if params:
            default_params.update(params)
        super().__init__(name="波动收缩突破策略", params=default_params)

    def get_description(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": "1.0.0",
            "concept": "依据经典 VCP 波动收缩模型，在标的价格振幅逐步收窄、成交量显著萎缩的洗盘末端，捕捉放量打破平静、启动新一轮主升浪的入场点。",
            "entry_conditions": [
                f"波动深度收缩：布林带宽收敛至 {self.params['max_bandwidth']*100:.0f}% 以内，表明筹码趋于沉淀一致",
                "底部逐步抬高：近期 5 日最低点高于前 15 日最低点，呈现重心上移",
                f"打破平静放量：当日成交量达到 20 日均量的 {self.params['vol_breakout_mult']:.2f} 倍以上",
                "站稳均线：收盘价站上 EMA(20) 与 EMA(50)，均线呈现发散萌芽",
            ],
            "exit_conditions": [
                "止损退出：收盘价跌破收缩平台底部或入场价下方 1.2*ATR",
                "跟踪止盈：达到目标盈亏比 (2.5 倍风险) 分批止盈，跌破 10 日均线清仓",
                "假突破失效：突破后 3 日内缩量阴跌重新跌回平台中轴，立即主动止损",
            ],
            "parameters": self.params,
        }

    def evaluate_latest(self, df: pd.DataFrame, symbol: str) -> StrategySignal:
        if len(df) < 60:
            return StrategySignal(
                symbol=symbol,
                date=df["date"].iloc[-1] if len(df) > 0 and "date" in df else "",
                signal_type=SignalType.NONE,
                strategy_name=self.name,
                conditions_pending=["历史日线不足 60 根，无法确认波动收缩形态"],
            )

        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        date_str = str(row["date"])[:10]
        close = float(row.get("close", 0.0))
        open_p = float(row.get("open", 0.0))
        atr = float(row.get("atr_14", close * 0.03))
        ema20 = float(row.get("ema_20", close))
        ema50 = float(row.get("ema_50", close))
        vol = float(row.get("volume", 0.0))
        vol_ma20 = float(row.get("vol_ma20", 1.0))
        boll_w = float(prev_row.get("boll_width", 0.25))

        factors = compute_stock_factors(df, symbol)
        certainty = factors.certainty_score if factors else 50.0

        conditions_met = []
        conditions_pending = []
        risks = []

        # 条件 1: 波动收缩
        if boll_w <= self.params["max_bandwidth"]:
            conditions_met.append(f"波动率充分收敛 (突破前布林带宽 {boll_w*100:.1f}% ≤ {self.params['max_bandwidth']*100:.0f}%)")
        else:
            conditions_pending.append(f"波动率尚未充分收敛 (布林带宽 {boll_w*100:.1f}% > {self.params['max_bandwidth']*100:.0f}%)")

        # 条件 2: 底部抬高
        low_5 = df["low"].iloc[-5:].min()
        low_15 = df["low"].iloc[-20:-5].min() if len(df) >= 20 else low_5
        if low_5 >= low_15 * 0.99:
            conditions_met.append(f"形态重心稳步抬高 (近期低点 {low_5:.2f} ≥ 前期低点 {low_15:.2f})")
        else:
            conditions_pending.append(f"近期重心走低，尚未构筑企稳平台")

        # 条件 3: 放量爆发
        vol_req = vol_ma20 * self.params["vol_breakout_mult"]
        if vol >= vol_req and close > open_p:
            conditions_met.append(f"放量阳线启动突破 (成交量 {vol/100:.0f}手 ≥ 均量的 {self.params['vol_breakout_mult']:.2f}倍)")
        else:
            conditions_pending.append(f"未见放量阳线确认 (当日量比 {vol/vol_ma20:.2f}，需 ≥ {self.params['vol_breakout_mult']:.2f})")

        # 条件 4: 站在均线之上
        if close > ema20 and close > ema50:
            conditions_met.append("价格收于中期均线组上方")
        else:
            conditions_pending.append("收盘价尚未突破并站稳中期均线")

        # 止损止盈
        stop_loss_price = round(max(low_5 - (atr * 0.5), close - (atr * self.params["atr_multiplier"])), 2)
        take_profit_price = round(close + (close - stop_loss_price) * self.params["risk_reward_ratio"], 2)

        risks.append("假突破风险：收缩后的假突破常伴随迅速反杀，跌破平台底部需坚决止损")
        risks.append("流动性风险：长期收缩的冷门标的在破位时可能出现流动性折价")

        signal_type = SignalType.BUY if len(conditions_pending) == 0 else SignalType.NONE

        return StrategySignal(
            symbol=symbol,
            date=date_str,
            signal_type=signal_type,
            strategy_name=self.name,
            candidate_entry_price=round(close, 2),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            stop_loss_rationale=f"以收缩平台底部 {low_5:.2f} 缓冲 ATR 测算防守底线 {stop_loss_price:.2f}",
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            risks=risks,
            priority_score=certainty,
            metrics={"boll_width": boll_w, "vol_ratio": vol / vol_ma20 if vol_ma20 > 0 else 1.0, "certainty": certainty},
        )

    def generate_signals(self, df: pd.DataFrame, symbol: str) -> List[StrategySignal]:
        signals = []
        if len(df) < 60:
            return signals
        for i in range(60, len(df)):
            sub_df = df.iloc[: i + 1]
            sig = self.evaluate_latest(sub_df, symbol)
            if sig.is_actionable:
                signals.append(sig)
        return signals
