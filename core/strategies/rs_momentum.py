"""
相对强度动量策略 (Relative Strength Momentum Strategy)
适用风格: 捕捉跑赢基准指数的市场领涨波段标的
核心理念: “选强不选弱，顺势买入相对全市场与行业走强的龙头，在动能衰竭时止盈”
"""

from typing import Any, Dict, List, Optional
import pandas as pd
from core.factors import compute_stock_factors
from core.strategies.base import BaseStrategy, SignalType, StrategySignal


class RSMomentumStrategy(BaseStrategy):
    """相对强度动量观察策略"""

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        default_params = {
            "min_rs_score": 65.0,  # 相对强度得分下限
            "momentum_days": 20,  # 动量观察周期
            "min_momentum_ret": 0.03,  # 20日涨幅至少 3%
            "atr_multiplier": 1.2,  # 止损 ATR 乘数
            "risk_reward_ratio": 2.5,  # 目标盈亏比
        }
        if params:
            default_params.update(params)
        super().__init__(name="相对强度动量策略", params=default_params)

    def get_description(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": "1.0.0",
            "concept": "基于量化相对强度 (RS) 因子，只在标的显著跑赢基准指数且处于健康动量区间时介入，享受强者恒强的动量溢价。",
            "entry_conditions": [
                f"相对强度达标：标的综合相对强度得分 ≥ {self.params['min_rs_score']:.1f}，在市场中处于优势分位数",
                f"动量趋势健康：过去 {self.params['momentum_days']} 日涨幅 ≥ {self.params['min_momentum_ret']*100:.1f}%，收盘价站上 EMA(20)",
                "未过度透支：RSI(14) 处于 45 ~ 75 区间，既有向上动能又未陷入极端钝化超买",
                "放量确认：成交量达到 20 日均量的 1.05 倍以上",
            ],
            "exit_conditions": [
                "止损退出：收盘价跌破近期低点下方 1.2*ATR 或收盘跌破 EMA(50)",
                "跟踪止盈：达到目标盈亏比 (2.5 倍风险) 分批落袋；若 20 日动量由正转负且跌破 20 日均线清仓",
                "失效条件：买入后 5 个交易日内相对大盘出现显著补跌，及时斩仓",
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
                conditions_pending=["历史日线不足 60 根，无法计算动量与相对强度"],
            )

        row = df.iloc[-1]
        date_str = str(row["date"])[:10]
        close = float(row.get("close", 0.0))
        open_p = float(row.get("open", 0.0))
        atr = float(row.get("atr_14", close * 0.03))
        ema20 = float(row.get("ema_20", close))
        ema50 = float(row.get("ema_50", close))
        rsi = float(row.get("rsi_14", 50.0))
        vol = float(row.get("volume", 0.0))
        vol_ma20 = float(row.get("vol_ma20", 1.0))

        factors = compute_stock_factors(df, symbol)
        rs_score = factors.rs_score if factors else 50.0
        certainty = factors.certainty_score if factors else 50.0

        p20_close = float(df.iloc[-20].get("close", close)) if len(df) >= 20 else close
        ret20 = (close - p20_close) / p20_close if p20_close > 0 else 0.0

        conditions_met = []
        conditions_pending = []
        risks = []

        # 条件 1: 相对强度
        if rs_score >= self.params["min_rs_score"]:
            conditions_met.append(f"相对强度优异 (RS 得分 {rs_score:.1f} ≥ {self.params['min_rs_score']:.1f})")
        else:
            conditions_pending.append(f"相对强度较弱 (当前 RS 得分 {rs_score:.1f} < {self.params['min_rs_score']:.1f})")

        # 条件 2: 动量与趋势
        if ret20 >= self.params["min_momentum_ret"] and close > ema20:
            conditions_met.append(f"20日价格动量充沛 (收益率 +{ret20*100:.1f}% 且站上 EMA20)")
        else:
            conditions_pending.append(f"动量不足或未站上 EMA20 (20日涨幅 {ret20*100:.1f}%)")

        # 条件 3: RSI 动能
        if 45.0 <= rsi <= 75.0:
            conditions_met.append(f"RSI 动量适中 (RSI={rsi:.1f})")
        else:
            conditions_pending.append(f"RSI 未处于健康动能区间 (当前 RSI={rsi:.1f})")

        # 条件 4: 放量
        if vol >= vol_ma20 * 1.05:
            conditions_met.append(f"成交量温和放量 (量比 {vol/vol_ma20:.2f})")
        else:
            conditions_pending.append("成交量不足 20 日均量的 1.05 倍")

        # 止损止盈
        recent_low = df["low"].iloc[-10:].min()
        stop_loss_price = round(max(recent_low - (atr * 0.5), close - (atr * self.params["atr_multiplier"])), 2)
        take_profit_price = round(close + (close - stop_loss_price) * self.params["risk_reward_ratio"], 2)

        risks.append("强势股补跌风险：大盘急跌阶段强势股常出现补跌补跌跌停")
        risks.append("高波动风险：动量策略在震荡市中可能发生频繁假突破止损")

        signal_type = SignalType.BUY if len(conditions_pending) == 0 else SignalType.NONE

        return StrategySignal(
            symbol=symbol,
            date=date_str,
            signal_type=signal_type,
            strategy_name=self.name,
            candidate_entry_price=round(close, 2),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            stop_loss_rationale=f"以近期波段低点缓冲 ATR 测算动量防守位 {stop_loss_price:.2f}",
            conditions_met=conditions_met,
            conditions_pending=conditions_pending,
            risks=risks,
            priority_score=certainty,
            metrics={"rs_score": rs_score, "ret_20": ret20, "rsi": rsi, "certainty": certainty},
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
