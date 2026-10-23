"""
区间突破观察策略 (Range Breakout Strategy)
适用风格: 箱体震荡结束、启动新一轮波段主升浪的趋势跟踪交易
核心理念: “买在阻力被有效击穿、波动率放大、成交量显著放大的拐点”
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from core.strategies.base import BaseStrategy, SignalType, StrategySignal


class RangeBreakoutStrategy(BaseStrategy):
    """
    区间突破观察策略
    结合唐奇安通道、布林带宽挤压 (Squeeze) 与成交量异动确认
    """

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        default_params = {
            "channel_period": 20,  # 箱体/通道观测周期 (唐奇安通道)
            "squeeze_bandwidth": 0.22,  # 突破前的波动率压缩门槛 (布林带宽 ≤ 22%)
            "vol_breakout_mult": 1.75,  # 突破放量倍数 (较20日均量)
            "max_rsi": 82.0,  # 动能过热上限过滤
            "atr_multiplier": 1.5,  # 止损 ATR 乘数
            "risk_reward_ratio": 2.5,  # 目标盈亏比
        }
        if params:
            default_params.update(params)
        super().__init__(name="区间突破观察策略", params=default_params)

    def get_description(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": "1.0.0",
            "concept": "标的经历一定周期的箱体横盘蓄势与波动率收敛后，收盘价强力穿透前期区间阻力位，且伴随量能急剧放大，提示新一轮波段趋势展开。",
            "entry_conditions": [
                f"区间蓄势收敛：突破前经历至少 {self.params['channel_period']} 个交易日的震荡整理，布林带宽收敛至 {self.params['squeeze_bandwidth']*100:.0f}% 以内",
                f"价格穿透突破：收盘价有效突破过去 {self.params['channel_period']} 日唐奇安通道上轨 (过去 N 日最高收盘/高点)",
                f"阳线收盘坚挺：突破当日收实体阳线 (Close > Open)，且收盘位于全天振幅的高位区间 (收盘价接近当日最高价)",
                f"成交量倍量脉冲：突破当日成交量达到 20 日均量的 {self.params['vol_breakout_mult']:.2f} 倍以上，确认主力资金真实推升意图",
                f"未极度透支：RSI(14) 尚未超过 {self.params['max_rsi']}，避免在纯高位追高接盘",
            ],
            "exit_conditions": [
                "止损退出：收盘价跌破箱体突破位或跌破入场价下方 1.5 倍 ATR",
                "跟踪止盈：达到目标盈亏比 (2.5 倍风险) 执行减仓；余仓以 10 日均线或跌破前 5 日最低点作为跟踪止盈线",
                "假突破失效：若突破后 2 个交易日内收盘价重新跌回原箱体中轨下方，判定为假突破诱多，无条件清仓止损",
            ],
            "parameters": self.params,
        }

    def evaluate_latest(self, df: pd.DataFrame, symbol: str) -> StrategySignal:
        min_bars = self.params["channel_period"] + 20
        if len(df) < min_bars:
            return StrategySignal(
                symbol=symbol,
                date=df["date"].iloc[-1] if len(df) > 0 and "date" in df else "",
                signal_type=SignalType.NONE,
                strategy_name=self.name,
                conditions_pending=[f"数据不足，至少需要 {min_bars} 根历史日线数据计算唐奇安通道与布林带宽"],
                risks=["样本历史过短，无法验证箱体整理周期"],
            )

        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        date_str = str(row["date"])[:10]

        close = row.get("close", 0.0)
        open_p = row.get("open", 0.0)
        high = row.get("high", 0.0)
        low = row.get("low", 0.0)
        vol = row.get("volume", 0.0)
        vol_ma20 = row.get("vol_ma20", 1.0)
        atr = row.get("atr_14", close * 0.03)
        rsi = row.get("rsi_14", 50.0)
        donchian_up = row.get("donchian_up_20", 0.0)
        boll_w = prev_row.get("boll_width", 0.3)

        conditions_met = []
        conditions_pending = []
        risks = []

        # 条件 1: 突破唐奇安通道上轨
        breakout_ok = close > donchian_up and donchian_up > 0
        if breakout_ok:
            conditions_met.append(f"价格强势突破 {self.params['channel_period']} 日箱体阻力 (收盘={close:.2f} > 阻力位={donchian_up:.2f})")
        else:
            conditions_pending.append(f"尚未突破箱体上轨 (当前收盘={close:.2f}，箱体阻力={donchian_up:.2f})")

        # 条件 2: 实体阳线强劲
        candle_ratio = (close - open_p) / (high - low) if (high - low) > 0 else 0.5
        candle_ok = (close > open_p) and (candle_ratio >= 0.5)
        if candle_ok:
            conditions_met.append(f"收出坚挺中大阳线 (阳线实体占振幅 {candle_ratio*100:.0f}%)")
        else:
            conditions_pending.append("K线形态未达强实体阳线标准 (存在较长上影线或收阴)")

        # 条件 3: 放量倍量脉冲
        vol_req = vol_ma20 * self.params["vol_breakout_mult"]
        vol_ok = vol >= vol_req
        if vol_ok:
            conditions_met.append(f"成交量显著倍量爆发 (当日 {vol/100:.0f}手 ≥ 20日均量 {vol_ma20/100:.0f}手的 {self.params['vol_breakout_mult']:.2f}倍)")
        else:
            conditions_pending.append(f"成交量未达放量突破标准 (当日 {vol/100:.0f}手，需达到 {vol_req/100:.0f}手)")

        # 条件 4: 前期波动率收敛
        squeeze_ok = boll_w <= self.params["squeeze_bandwidth"]
        if squeeze_ok:
            conditions_met.append(f"前期箱体蓄势充分 (突破前布林带宽 {boll_w*100:.1f}% ≤ {self.params['squeeze_bandwidth']*100:.0f}%)")
        else:
            conditions_pending.append(f"前期波动率未完全收敛 (布林带宽 {boll_w*100:.1f}% > {self.params['squeeze_bandwidth']*100:.0f}%)，需防范震荡市中的假突破")

        # 条件 5: RSI 尚未极度超买透支
        rsi_ok = rsi <= self.params["max_rsi"]
        if rsi_ok:
            conditions_met.append(f"动能未过热透支 (当前 RSI={rsi:.1f} ≤ {self.params['max_rsi']})")
        else:
            conditions_pending.append(f"RSI 处于极度超买风险区 (RSI={rsi:.1f} > {self.params['max_rsi']})，防短线急拉后诱多见顶")

        # 计算止损与止盈
        # 止损：以突破箱体上轨下方 0.8*ATR 或入场价下方 1.5*ATR
        stop_dist = max(atr * self.params["atr_multiplier"], close * 0.035)
        stop_loss_price = round(max(donchian_up - (atr * 0.5), close - stop_dist), 2)
        take_profit_price = round(close + (close - stop_loss_price) * self.params["risk_reward_ratio"], 2)

        stop_loss_rationale = (
            f"以箱体突破位 {donchian_up:.2f} 允许回踩容错 (0.5*ATR) 及当前价格下方 {self.params['atr_multiplier']} 倍 ATR "
            f"({stop_dist:.2f} 元) 计算止损，跌破突破口即行离场"
        )

        risks.append("假突破风险：A 股市场箱体突破后经常面临回踩考验，若次日反包跌破突破位需果断认赔")
        risks.append("涨跌停成交限制：若当日或次日开盘一字涨停无法买入，切勿在盘中盲目高位扫板")
        risks.append("跳空低开风险：若公司突发负面公告低开跳空跌破止损线，实际止损价将受滑点影响")

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
                "donchian_up": donchian_up,
                "boll_width": boll_w,
                "rsi_14": rsi,
                "atr_14": atr,
                "vol_ratio_20": round(vol / vol_ma20, 2) if vol_ma20 > 0 else 1.0,
            },
        )

    def generate_signals(self, df: pd.DataFrame, symbol: str) -> List[StrategySignal]:
        signals = []
        min_bars = self.params["channel_period"] + 20
        if len(df) < min_bars:
            return signals

        for i in range(min_bars, len(df)):
            sub_df = df.iloc[: i + 1]
            sig = self.evaluate_latest(sub_df, symbol)
            if sig.is_actionable:
                signals.append(sig)

        return signals
