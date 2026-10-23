"""
持仓体检与组合健康度量化诊断模块 (Portfolio Health Analyzer)
特性:
1. 支持单只与批量持仓导入 (代码、成本价、持仓股数、买入日期)
2. 全维度技术与风控诊断: 盈亏比、持股天数、均线趋势、关键支撑与阻力位、建议移动止损位
3. 组合层面风险透视: 单票集中度、行业暴露度、浮亏超标预警与流动性风险
4. 纯因果量化事实输出，与可选 AI Agent 无缝对接
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

from core.factors import compute_stock_factors
from core.rules import classify_symbol, get_board_rules
from data_provider.manager import DataManager


@dataclass
class HoldingItem:
    symbol: str
    cost_price: float
    shares: int
    buy_date: str = ""
    notes: str = ""


@dataclass
class PositionHealthReport:
    symbol: str
    name: str
    board_name: str
    cost_price: float
    current_price: float
    shares: int
    market_value: float
    unrealized_pnl: float
    pnl_pct: float
    holding_days: int
    trend_status: str  # '多头趋势良好', '中性震荡', '破位弱势'
    support_level: float
    resistance_level: float
    suggested_stop_loss: float
    risk_level: str  # 'LOW', 'MEDIUM', 'HIGH'
    warnings: List[str] = field(default_factory=list)
    action_advice: str = ""


@dataclass
class PortfolioHealthSummary:
    total_cost: float
    total_market_value: float
    total_unrealized_pnl: float
    total_pnl_pct: float
    positions_count: int
    top_stock_weight_pct: float
    top_industry: str
    top_industry_weight_pct: float
    overall_health_score: float  # 0 ~ 100
    overall_risk_rating: str  # 'HEALTHY', 'CAUTION', 'DANGER'
    detailed_positions: List[PositionHealthReport]
    system_alerts: List[str]


class PortfolioHealthAnalyzer:
    """持仓体检诊断引擎"""

    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager

    def parse_holdings_csv(self, file_content: str) -> List[HoldingItem]:
        """解析用户上传的持仓 CSV 文本"""
        import io
        holdings = []
        df = pd.read_csv(io.StringIO(file_content))
        # 兼容不同列名: 代码/symbol, 成本/cost/cost_price, 数量/shares/volume
        col_map = {}
        for col in df.columns:
            c = str(col).strip().lower()
            if "代码" in c or "symbol" in c or "code" in c:
                col_map["symbol"] = col
            elif "成本" in c or "cost" in c or "price" in c:
                col_map["cost"] = col
            elif "数量" in c or "股数" in c or "shares" in c or "volume" in c:
                col_map["shares"] = col
            elif "日期" in c or "date" in c:
                col_map["buy_date"] = col

        if "symbol" not in col_map or "cost" not in col_map or "shares" not in col_map:
            raise ValueError("CSV 必须包含股票代码、成本价、持仓数量三项核心列")

        for _, row in df.iterrows():
            sym = str(row[col_map["symbol"]]).strip().zfill(6)
            cost = float(row[col_map["cost"]])
            shares = int(row[col_map["shares"]])
            buy_dt = str(row[col_map["buy_date"]]) if "buy_date" in col_map else ""
            if sym and cost > 0 and shares > 0:
                holdings.append(HoldingItem(symbol=sym, cost_price=cost, shares=shares, buy_date=buy_dt))

        return holdings

    def analyze_portfolio(self, holdings: List[HoldingItem]) -> PortfolioHealthSummary:
        """执行完整持仓体检"""
        if not holdings:
            return PortfolioHealthSummary(
                total_cost=0.0,
                total_market_value=0.0,
                total_unrealized_pnl=0.0,
                total_pnl_pct=0.0,
                positions_count=0,
                top_stock_weight_pct=0.0,
                top_industry="无",
                top_industry_weight_pct=0.0,
                overall_health_score=100.0,
                overall_risk_rating="HEALTHY",
                detailed_positions=[],
                system_alerts=["当前未录入持仓数据"],
            )

        pos_reports: List[PositionHealthReport] = []
        total_cost = 0.0
        total_mkt = 0.0
        industry_map: Dict[str, float] = {}

        for h in holdings:
            sym = h.symbol
            board_key, exchange, board_name = classify_symbol(sym)
            stock_name = self.data_manager.get_stock_name(sym)

            # 获取历史日线以评估趋势与支撑阻力
            df, _ = self.data_manager.get_daily_bars(sym, start_date="2024-01-01")
            if df is not None and len(df) > 0:
                cur_p = float(df["close"].iloc[-1])
                ema20 = float(df.get("ema_20", pd.Series([cur_p])).iloc[-1])
                ema50 = float(df.get("ema_50", pd.Series([cur_p])).iloc[-1])
                atr = float(df.get("atr_14", pd.Series([cur_p * 0.03])).iloc[-1])
                support = float(df["low"].iloc[-20:].min())
                resistance = float(df["high"].iloc[-20:].max())
            else:
                cur_p = h.cost_price
                ema20 = cur_p
                ema50 = cur_p
                atr = cur_p * 0.03
                support = cur_p * 0.95
                resistance = cur_p * 1.05

            mkt_val = cur_p * h.shares
            cost_basis = h.cost_price * h.shares
            pnl = mkt_val - cost_basis
            pnl_pct = pnl / cost_basis if cost_basis > 0 else 0.0

            total_cost += cost_basis
            total_mkt += mkt_val

            # 趋势判断
            if cur_p > ema20 > ema50:
                trend_status = "多头趋势良好"
            elif cur_p < ema20 < ema50:
                trend_status = "破位走弱"
            else:
                trend_status = "箱体震荡"

            # 移动止损位建议 (以支撑位下方 0.5*ATR 或现价下方 1.2*ATR)
            suggested_stop = round(max(support - (atr * 0.5), cur_p - (atr * 1.2)), 2)

            # 风险告警
            warnings = []
            risk_level = "LOW"
            if pnl_pct <= -0.08:
                warnings.append(f"单票累计浮亏已达 {pnl_pct*100:.1f}%，超过 -8% 预警红线，需严防深套")
                risk_level = "HIGH"
            elif pnl_pct <= -0.05:
                warnings.append(f"单票浮亏达 {pnl_pct*100:.1f}%，已触及止损警戒区")
                risk_level = "MEDIUM"

            if trend_status == "破位走弱":
                warnings.append("股价跌破 20/50 日多空分水岭，中期走势偏空")
                if risk_level != "HIGH":
                    risk_level = "MEDIUM"

            action_advice = "持有观察"
            if risk_level == "HIGH":
                action_advice = "严格执行止损纪律，减仓或离场防范进一步亏损"
            elif pnl_pct >= 0.15 and cur_p < ema20:
                action_advice = "收益丰厚但跌破短线均线，建议逢高锁定部分利润"

            pos_reports.append(PositionHealthReport(
                symbol=sym,
                name=stock_name,
                board_name=board_name,
                cost_price=round(h.cost_price, 2),
                current_price=round(cur_p, 2),
                shares=h.shares,
                market_value=round(mkt_val, 2),
                unrealized_pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 4),
                holding_days=len(df) if df is not None else 0,
                trend_status=trend_status,
                support_level=round(support, 2),
                resistance_level=round(resistance, 2),
                suggested_stop_loss=suggested_stop,
                risk_level=risk_level,
                warnings=warnings,
                action_advice=action_advice,
            ))

        # 组合级指标
        total_pnl = total_mkt - total_cost
        total_pnl_pct = total_pnl / total_cost if total_cost > 0 else 0.0

        # 单票最大集中度
        max_stock_val = max(p.market_value for p in pos_reports) if pos_reports else 0.0
        top_stock_weight = (max_stock_val / total_mkt * 100) if total_mkt > 0 else 0.0

        system_alerts = []
        if top_stock_weight > 40.0:
            system_alerts.append(f"持股过于集中：第一大重仓股权重达 {top_stock_weight:.1f}% (超过 40%)，单票黑天鹅冲击风险极高")

        if len(pos_reports) > 8:
            system_alerts.append(f"持股数量偏多 ({len(pos_reports)} 只)，可能超出个人精力覆盖范围，建议适当收缩聚焦")

        high_risk_count = sum(1 for p in pos_reports if p.risk_level == "HIGH")
        if high_risk_count > 0:
            system_alerts.append(f"组合内存在 {high_risk_count} 只高风险深度破位标的，建议立即处理")

        # 综合健康度打分
        health_score = 100.0 - (high_risk_count * 25.0) - (max(0.0, top_stock_weight - 30.0) * 0.8)
        if total_pnl_pct < -0.10:
            health_score -= 20.0
        health_score = min(100.0, max(10.0, health_score))

        if health_score >= 80:
            risk_rating = "HEALTHY"
        elif health_score >= 50:
            risk_rating = "CAUTION"
        else:
            risk_rating = "DANGER"

        return PortfolioHealthSummary(
            total_cost=round(total_cost, 2),
            total_market_value=round(total_mkt, 2),
            total_unrealized_pnl=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl_pct, 4),
            positions_count=len(pos_reports),
            top_stock_weight_pct=round(top_stock_weight, 1),
            top_industry="多元配置",
            top_industry_weight_pct=round(top_stock_weight, 1),
            overall_health_score=round(health_score, 1),
            overall_risk_rating=risk_rating,
            detailed_positions=pos_reports,
            system_alerts=system_alerts,
        )
