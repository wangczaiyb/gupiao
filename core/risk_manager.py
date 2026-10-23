"""
风险管理与动态仓位控制模块
支持模拟资金、单笔最大允许风险百分比、ATR 止损距离自适应仓位计算
严格执行板块交易数量规则 (整手/递增单位)、单票仓位上限、行业集中度与组合最大持仓数约束
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from core.rules import round_trade_quantity, calculate_trade_cost, classify_symbol, get_board_rules


@dataclass
class RiskBudgetConfig:
    total_capital: float = 5000.0  # 模拟资金总额 (默认小资金 5000 元，支持自定义)
    risk_per_trade_pct: float = 0.015  # 单笔允许最大本金亏损比例 (默认 1.5%)
    max_single_stock_pct: float = 0.25  # 单只股票持仓金额占总资金上限 (默认 25%)
    max_total_position_pct: float = 0.85  # 组合总持仓上限 (默认 85%，保留 15% 现金安全垫)
    max_concurrent_positions: int = 5  # 最大允许同时持仓股票只数
    max_industry_exposure_pct: float = 0.40  # 单一行业最大暴露度 (默认 40%)
    max_drawdown_stop_trading_pct: float = 0.15  # 组合累计回撤达到此阈值时强制暂停开仓警报
    commission_rate: float = 0.00025  # 佣金率
    min_commission: float = 5.0  # 最低佣金 (可配置 0/1/5 元)
    user_permissions: Dict[str, bool] = field(default_factory=lambda: {
        "SH_MAIN": True,
        "SZ_MAIN": True,
        "CHINEXT": True,
        "STAR": False,
        "BSE": False,
    })



@dataclass
class PositionSizeProposal:
    symbol: str
    entry_price: float
    stop_loss_price: float
    risk_per_share: float  # 每股风险距离 (元)
    recommended_shares: int  # 建议买入股数 (经交易所申报规则规整)
    recommended_amount: float  # 预估买入金额 (元)
    position_pct_of_capital: float  # 占总资产比例
    estimated_loss_at_stop: float  # 触发止损时的预估亏损额 (含双边交易费用)
    estimated_loss_pct_of_capital: float  # 占总资产百分比
    fee_estimate: float  # 预估交易手续费
    checks_passed: bool  # 风控检查是否全额通过
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    risk_warnings: List[str] = field(default_factory=list)


class RiskManager:
    """风控与仓位计算引擎"""

    def __init__(self, config: Optional[RiskBudgetConfig] = None):
        self.config = config or RiskBudgetConfig()

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        current_cash: float,
        current_positions: Dict[str, Dict],  # {symbol: {'shares': 1000, 'cost': 15.0, 'market_val': 16000, 'industry': '电子'}}
        industry: str = "其他",
        current_peak_capital: Optional[float] = None,
    ) -> PositionSizeProposal:
        """
        基于固定风险百分比与止损距离计算合规仓位
        """
        passed_checks = []
        failed_checks = []
        warnings = []

        total_capital = self.config.total_capital
        if entry_price <= 0 or stop_loss_price <= 0:
            return PositionSizeProposal(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                risk_per_share=0.0,
                recommended_shares=0,
                recommended_amount=0.0,
                position_pct_of_capital=0.0,
                estimated_loss_at_stop=0.0,
                estimated_loss_pct_of_capital=0.0,
                fee_estimate=0.0,
                checks_passed=False,
                failed_checks=["入场价或止损价必须大于 0"],
            )

        # 检查 1: 止损价必须严格低于入场价 (对于做多波段)
        if stop_loss_price >= entry_price:
            return PositionSizeProposal(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                risk_per_share=0.0,
                recommended_shares=0,
                recommended_amount=0.0,
                position_pct_of_capital=0.0,
                estimated_loss_at_stop=0.0,
                estimated_loss_pct_of_capital=0.0,
                fee_estimate=0.0,
                checks_passed=False,
                failed_checks=["多头止损价必须严格低于入场参考价"],
            )

        # 检查板块交易权限
        board_key, _, board_name = classify_symbol(symbol)
        if not self.config.user_permissions.get(board_key, True):
            failed_checks.append(f"板块权限限制：当前账户未勾选开通 [{board_name}] 交易权限，禁止开仓")

        risk_per_share = entry_price - stop_loss_price
        stop_loss_ratio = risk_per_share / entry_price

        # 止损幅度警告 (如止损过大或过小)
        if stop_loss_ratio > 0.10:
            warnings.append(f"止损幅度偏大 ({stop_loss_ratio*100:.1f}%)，一旦跳空低开实际亏损将放大")
        elif stop_loss_ratio < 0.02:
            warnings.append(f"止损幅度过窄 ({stop_loss_ratio*100:.1f}%)，容易被盘中正常噪波击穿止损")

        # 检查 2: 当前持仓只数限制
        num_existing = len(current_positions)
        if symbol not in current_positions and num_existing >= self.config.max_concurrent_positions:
            failed_checks.append(
                f"持仓只数已达上限 ({num_existing}/{self.config.max_concurrent_positions} 只)，禁止开辟新标的"
            )
        else:
            passed_checks.append(f"持仓只数检查通过 (当前 {num_existing} 只，上限 {self.config.max_concurrent_positions} 只)")

        # 检查 3: 组合回撤风控停牌预警
        if current_peak_capital and current_peak_capital > total_capital:
            drawdown = (current_peak_capital - total_capital) / current_peak_capital
            if drawdown >= self.config.max_drawdown_stop_trading_pct:
                failed_checks.append(
                    f"组合累计回撤已达 {drawdown*100:.1f}%，超过安全熔断红线 {self.config.max_drawdown_stop_trading_pct*100:.1f}%，触发停止开仓保护"
                )
            else:
                passed_checks.append(f"组合回撤受控 ({drawdown*100:.1f}% < 警戒线 {self.config.max_drawdown_stop_trading_pct*100:.1f}%)")

        # 理论最大允许本金损失金额
        max_allowed_loss = total_capital * self.config.risk_per_trade_pct

        # 理论最大股数 = 允许损失金额 / 每股风险距离
        raw_shares = max_allowed_loss / risk_per_share

        # 理论单票金额上限约束
        single_stock_max_amount = total_capital * self.config.max_single_stock_pct
        shares_by_single_limit = single_stock_max_amount / entry_price

        # 理论现有现金约束
        shares_by_cash = current_cash / (entry_price * 1.002)  # 留存千分之二手续费安全垫

        # 现有行业集中度约束
        industry_current_val = sum(
            pos.get("market_val", 0.0) for pos in current_positions.values() if pos.get("industry") == industry
        )
        industry_max_amount = total_capital * self.config.max_industry_exposure_pct
        industry_remaining_amount = max(0.0, industry_max_amount - industry_current_val)
        shares_by_industry = industry_remaining_amount / entry_price

        # 取各约束的最小值
        capped_shares = min(raw_shares, shares_by_single_limit, shares_by_cash, shares_by_industry)

        # 按照板块申报规则规范化申报股数 (整手 / 科创板200起 / 北交所100起)
        valid_shares = round_trade_quantity(int(capped_shares), symbol, is_buy=True)

        if valid_shares <= 0:
            try:
                board_rule = get_board_rules(symbol)
                min_buy_qty = board_rule.min_buy_qty
            except Exception:
                min_buy_qty = 100

            min_lot_cash = min_buy_qty * entry_price
            if min_lot_cash > current_cash:
                failed_checks.append(
                    f"整手资金不足：该标的最低申报 {min_buy_qty} 股，买入一手需 {min_lot_cash:.2f} 元，超过当前可用现金 {current_cash:.2f} 元"
                )
            elif min_lot_cash > single_stock_max_amount:
                failed_checks.append(
                    f"整手超单票上限：一手所需资金 {min_lot_cash:.2f} 元超过单票上限 {single_stock_max_amount:.2f} 元"
                )
            else:
                failed_checks.append(
                    f"单笔风险预算限制：根据单笔风险比例 {self.config.risk_per_trade_pct*100:.1f}%，计算出的股数未达最低申报量 {min_buy_qty} 股"
                )
            valid_shares = 0

        trade_amount = valid_shares * entry_price
        position_pct = trade_amount / total_capital if total_capital > 0 else 0.0

        # 计算双边费用与预估实际亏损
        buy_fee = calculate_trade_cost(
            trade_amount,
            is_buy=True,
            commission_rate=self.config.commission_rate,
            min_commission=self.config.min_commission,
        )
        sell_amount_stop = valid_shares * stop_loss_price
        sell_fee = calculate_trade_cost(
            sell_amount_stop,
            is_buy=False,
            commission_rate=self.config.commission_rate,
            min_commission=self.config.min_commission,
        )
        total_fees = buy_fee.total_fee + sell_fee.total_fee

        if trade_amount > 0 and (total_fees / trade_amount) > 0.003:
            warnings.append(
                f"小资金交易规费占比较高：预估双边费用 ({total_fees:.2f}元) 占成交金额比例达 {total_fees/trade_amount*100:.2f}% (受最低佣金 {self.config.min_commission:.1f}元 影响)，易侵蚀波段利润"
            )

        loss_at_stop = (valid_shares * risk_per_share) + total_fees
        loss_pct = loss_at_stop / total_capital if total_capital > 0 else 0.0


        # 细化风控检查结果
        if trade_amount > current_cash:
            failed_checks.append(f"所需资金 {trade_amount:.2f} 元超过当前可用现金 {current_cash:.2f} 元")
        else:
            passed_checks.append(f"现金充足 (所需 {trade_amount:.2f} 元，可用 {current_cash:.2f} 元)")

        if position_pct > self.config.max_single_stock_pct + 0.001:
            failed_checks.append(f"单票占比 {position_pct*100:.1f}% 超过上限 {self.config.max_single_stock_pct*100:.0f}%")
        else:
            passed_checks.append(f"单票仓位受控 (占比 {position_pct*100:.1f}% ≤ {self.config.max_single_stock_pct*100:.0f}%)")

        if industry_current_val + trade_amount > industry_max_amount:
            failed_checks.append(f"所属行业 [{industry}] 累计暴露将达 {(industry_current_val+trade_amount)/total_capital*100:.1f}%，超上限 {self.config.max_industry_exposure_pct*100:.0f}%")
        else:
            passed_checks.append(f"行业分散度合格 (行业 [{industry}] 预计占比 {(industry_current_val+trade_amount)/total_capital*100:.1f}%)")

        # 风险提示
        warnings.append("止损无法保证以预设价格成交：若开盘跳空低开或无量跌停，必须以真实可成交价格退出")
        warnings.append("模拟盘资金明确标记为【模拟资金】，仅供策略演练与风险测算使用")

        checks_passed = len(failed_checks) == 0 and valid_shares > 0

        return PositionSizeProposal(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_per_share=round(risk_per_share, 2),
            recommended_shares=valid_shares,
            recommended_amount=round(trade_amount, 2),
            position_pct_of_capital=round(position_pct, 4),
            estimated_loss_at_stop=round(loss_at_stop, 2),
            estimated_loss_pct_of_capital=round(loss_pct, 4),
            fee_estimate=round(total_fees, 2),
            checks_passed=checks_passed,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            risk_warnings=warnings,
        )
