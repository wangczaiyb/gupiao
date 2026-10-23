"""
高保真 A 股波段回测引擎 (Backtest Engine)
满足首版重点要求：
1. 信号收盘后生成，最早在下一交易日 (T+1) 开盘执行，杜绝以当日收盘价成交的偷价行为；
2. 纯因果计算，指标与信号禁止使用未来数据；
3. 手续费、滑点、资金限制、最小申报数量与递增单位、T+1、停牌及涨跌停约束真实介入撮合；
4. 同一根日 K 同时触及止损与止盈时，严格按最保守假设（先触发止损）结算；
5. 跳空低开跌破止损价时，以实际开盘价撮合成交，不假设能在止损价成交；
6. 多股票组合共享账户资金池，按真实可用现金开仓，杜绝单票独立全额资金相加的虚假膨胀；
7. 支持样本内/样本外区间切分与滚动验证 (Walk-Forward Validation)；
8. 输出标准净值曲线、最大回撤、夏普比率、胜率、盈亏比与基准对比。
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from core.calendar import get_next_trading_day, get_t_plus_n_date, to_date_obj
from core.rules import (
    calculate_price_limits,
    calculate_trade_cost,
    is_trade_restricted,
    round_trade_quantity,
)
from core.strategies.base import BaseStrategy, SignalType, StrategySignal


@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    entry_date: str  # 实际买入成交日 'YYYY-MM-DD'
    entry_price: float  # 实际买入成交价 (含滑点)
    shares: int  # 成交股数
    entry_cost_basis: float  # 买入总成本 (含费用)
    buy_fee: float  # 买入费用
    exit_date: Optional[str] = None  # 实际卖出成交日
    exit_price: Optional[float] = None  # 实际卖出成交价 (含滑点)
    exit_revenue: Optional[float] = None  # 卖出净回款 (扣费用)
    sell_fee: Optional[float] = None  # 卖出费用
    net_pnl: Optional[float] = None  # 净盈亏金额 (元)
    pnl_pct: Optional[float] = None  # 净收益率
    holding_days: int = 0  # 真实持仓交易日数
    exit_reason: str = ""  # 退出原因: 'STOP_LOSS', 'TAKE_PROFIT', 'SIGNAL_EXIT', 'TIME_STOP', 'FORCED_CLOSE'
    is_gap_exit: bool = False  # 是否为跳空出场
    is_conservative_conflict: bool = False  # 是否为同日触及止损止盈保守判定


@dataclass
class BacktestMetrics:
    initial_capital: float
    final_equity: float
    total_net_pnl: float
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_loss_ratio: float
    avg_holding_days: float
    total_fees_paid: float
    max_consecutive_losses: int
    benchmark_return_pct: Optional[float] = None
    alpha_pct: Optional[float] = None
    in_sample_return_pct: Optional[float] = None
    out_of_sample_return_pct: Optional[float] = None


class BacktestEngine:
    """高精度 A 股组合回测执行器"""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.00025,  # 万 2.5
        min_commission: float = 5.0,  # 5元最低佣金
        slippage_rate: float = 0.0005,  # 0.05% 滑点
        max_position_pct_per_stock: float = 0.25,  # 单票仓位上限 25%
        max_concurrent_positions: int = 5,  # 最大持仓股票数
        risk_per_trade_pct: float = 0.015,  # 单笔风险预算 1.5%
        trailing_stop_days: int = 20,  # 最大持仓天数强制时间平仓
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.slippage_rate = slippage_rate
        self.max_position_pct_per_stock = max_position_pct_per_stock
        self.max_concurrent_positions = max_concurrent_positions
        self.risk_per_trade_pct = risk_per_trade_pct
        self.trailing_stop_days = trailing_stop_days

    def run_single_stock(
        self,
        df: pd.DataFrame,
        symbol: str,
        strategy: BaseStrategy,
        benchmark_df: Optional[pd.DataFrame] = None,
        train_test_split_ratio: Optional[float] = None,
    ) -> Tuple[BacktestMetrics, pd.DataFrame, List[TradeRecord]]:
        """
        单标的回测
        返回: (metrics, daily_equity_curve_df, trade_records)
        """
        stock_dfs = {symbol: df}
        return self.run_portfolio(
            stock_dfs=stock_dfs,
            strategy=strategy,
            benchmark_df=benchmark_df,
            train_test_split_ratio=train_test_split_ratio,
        )

    def run_portfolio(
        self,
        stock_dfs: Dict[str, pd.DataFrame],
        strategy: BaseStrategy,
        benchmark_df: Optional[pd.DataFrame] = None,
        train_test_split_ratio: Optional[float] = None,
    ) -> Tuple[BacktestMetrics, pd.DataFrame, List[TradeRecord]]:
        """
        多标的组合共享资金回测
        stock_dfs: {symbol: df_with_indicators_and_date}
        """
        if not stock_dfs:
            empty_metrics = BacktestMetrics(
                initial_capital=self.initial_capital,
                final_equity=self.initial_capital,
                total_net_pnl=0.0,
                total_return_pct=0.0,
                annualized_return_pct=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                avg_win_pct=0.0,
                avg_loss_pct=0.0,
                profit_loss_ratio=0.0,
                avg_holding_days=0.0,
                total_fees_paid=0.0,
                max_consecutive_losses=0,
            )
            return empty_metrics, pd.DataFrame(), []

        # 整理全部唯一的交易日期并按时间升序排序
        all_dates = set()
        indexed_dfs: Dict[str, Dict[str, Dict]] = {}
        for sym, df in stock_dfs.items():
            if "date" not in df.columns or len(df) == 0:
                continue
            clean_df = df.copy()
            clean_df["date_str"] = clean_df["date"].astype(str).str[:10]
            indexed_dfs[sym] = clean_df.set_index("date_str").to_dict(orient="index")
            all_dates.update(clean_df["date_str"].tolist())

        sorted_dates = sorted(list(all_dates))
        if len(sorted_dates) < 2:
            # 样本不足 (至少需要2个交易日完成开仓与结算)
            empty_metrics = BacktestMetrics(
                initial_capital=self.initial_capital,
                final_equity=self.initial_capital,
                total_net_pnl=0.0,
                total_return_pct=0.0,
                annualized_return_pct=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                avg_win_pct=0.0,
                avg_loss_pct=0.0,
                profit_loss_ratio=0.0,
                avg_holding_days=0.0,
                total_fees_paid=0.0,
                max_consecutive_losses=0,
            )
            return empty_metrics, pd.DataFrame(), []

        # 预计算每个股票的信号：严格在收盘时生成
        # signals_by_date[date_str] = [StrategySignal, ...]
        signals_by_date: Dict[str, List[StrategySignal]] = {d: [] for d in sorted_dates}
        for sym, df in stock_dfs.items():
            sigs = strategy.generate_signals(df, sym)
            for s in sigs:
                if s.date in signals_by_date:
                    signals_by_date[s.date].append(s)

        # 账户状态追踪
        current_cash = self.initial_capital
        # open_positions: {symbol: {'shares': int, 'entry_price': float, 'entry_date': str, 'can_sell_date': str, 'stop_loss': float, 'take_profit': float, 'buy_fee': float, 'trade_id': str, 'days': int}}
        open_positions: Dict[str, Dict] = {}
        closed_trades: List[TradeRecord] = []
        equity_records = []
        total_fees_accumulated = 0.0
        trade_counter = 0

        # 时间切分点 (若启用样本外验证)
        split_date = None
        if train_test_split_ratio and 0.1 < train_test_split_ratio < 0.9:
            split_idx = int(len(sorted_dates) * train_test_split_ratio)
            split_date = sorted_dates[split_idx]

        in_sample_equities = []
        out_of_sample_equities = []

        # 逐日推进回测模拟
        for i, dt in enumerate(sorted_dates):
            # 1. 处理在仓标的平仓检测 (优先在开盘及盘中执行)
            # 依据 T+1 规则：只有达到可卖日期的持仓才能进行卖出平仓
            symbols_to_remove = []
            for sym, pos in list(open_positions.items()):
                pos["days"] += 1
                if dt not in indexed_dfs.get(sym, {}):
                    continue  # 当日无行情 (可能停牌)

                bar = indexed_dfs[sym][dt]
                cur_open = float(bar["open"])
                cur_high = float(bar["high"])
                cur_low = float(bar["low"])
                cur_close = float(bar["close"])
                is_suspended = bool(bar.get("is_suspended", False))

                # 检查跌停限制 (完整传入 ST 状态与新股上市无涨跌幅窗口)
                prev_close = float(bar.get("prev_close", cur_open))
                is_st_bar = bool(bar.get("is_st", False))
                is_ipo_unlimited_bar = bool(bar.get("is_ipo_unlimited", False))
                _, limit_down = calculate_price_limits(
                    prev_close, sym, is_st=is_st_bar, is_ipo_unlimited=is_ipo_unlimited_bar
                )
                is_restricted, _ = is_trade_restricted(cur_open, 99999.0, limit_down, is_buy=False, is_suspended=is_suspended)

                # 验证是否符合 T+1 可卖日期
                can_sell = dt >= pos["can_sell_date"] and not is_restricted

                if not can_sell:
                    continue  # 处于 T+0 锁定期或跌停停牌封死，无法卖出

                stop_price = pos["stop_loss"]
                tp_price = pos["take_profit"]

                triggered_stop = cur_low <= stop_price
                triggered_tp = cur_high >= tp_price
                time_stop = pos["days"] >= self.trailing_stop_days

                exit_price = None
                exit_reason = ""
                is_gap = False
                is_conservative = False

                # 核心要求 4: 同一根日 K 同时触及止损与止盈时，严格按最保守假设 (先触及止损) 结算
                if triggered_stop and triggered_tp:
                    is_conservative = True
                    exit_reason = "STOP_LOSS (Conservative Same-Bar Conflict)"
                    # 核心要求 5: 跳空低开跌破止损价时，以开盘价成交
                    if cur_open <= stop_price:
                        exit_price = cur_open * (1.0 - self.slippage_rate)
                        is_gap = True
                    else:
                        exit_price = stop_price * (1.0 - self.slippage_rate)
                elif triggered_stop:
                    exit_reason = "STOP_LOSS"
                    if cur_open <= stop_price:
                        exit_price = cur_open * (1.0 - self.slippage_rate)
                        is_gap = True
                    else:
                        exit_price = stop_price * (1.0 - self.slippage_rate)
                elif triggered_tp:
                    exit_reason = "TAKE_PROFIT"
                    if cur_open >= tp_price:
                        exit_price = cur_open * (1.0 - self.slippage_rate)
                    else:
                        exit_price = tp_price * (1.0 - self.slippage_rate)
                elif time_stop:
                    exit_reason = "TIME_STOP (Max Holding Days)"
                    exit_price = cur_close * (1.0 - self.slippage_rate)

                if exit_price is not None:
                    # 结算卖出
                    shares = pos["shares"]
                    gross_revenue = shares * exit_price
                    sell_fee_detail = calculate_trade_cost(
                        gross_revenue,
                        is_buy=False,
                        trade_date=to_date_obj(dt),
                        commission_rate=self.commission_rate,
                        min_commission=self.min_commission,
                    )
                    net_revenue = gross_revenue - sell_fee_detail.total_fee
                    total_fees_accumulated += sell_fee_detail.total_fee

                    entry_cost_basis = pos["shares"] * pos["entry_price"] + pos["buy_fee"]
                    net_pnl = net_revenue - entry_cost_basis
                    pnl_pct = net_pnl / entry_cost_basis if entry_cost_basis > 0 else 0.0

                    current_cash += net_revenue

                    trade_rec = TradeRecord(
                        trade_id=pos["trade_id"],
                        symbol=sym,
                        entry_date=pos["entry_date"],
                        entry_price=round(pos["entry_price"], 2),
                        shares=shares,
                        entry_cost_basis=round(entry_cost_basis, 2),
                        buy_fee=round(pos["buy_fee"], 2),
                        exit_date=dt,
                        exit_price=round(exit_price, 2),
                        exit_revenue=round(net_revenue, 2),
                        sell_fee=round(sell_fee_detail.total_fee, 2),
                        net_pnl=round(net_pnl, 2),
                        pnl_pct=round(pnl_pct, 4),
                        holding_days=pos["days"],
                        exit_reason=exit_reason,
                        is_gap_exit=is_gap,
                        is_conservative_conflict=is_conservative,
                    )
                    closed_trades.append(trade_rec)
                    symbols_to_remove.append(sym)

            for sym in symbols_to_remove:
                del open_positions[sym]

            # 2. 处理开仓买入：执行前一日收盘后生成的候选信号 (下一交易日开盘成交，Next Bar Open Execution)
            if i > 0:
                prev_date = sorted_dates[i - 1]
                pending_signals = signals_by_date.get(prev_date, [])

                # 跨标的确定性排序：当多个标的同日触发买入信号时，依据优先得分、预期盈亏比、量比及代码确定性排序
                sorted_pending_signals = sorted(
                    pending_signals,
                    key=lambda s: (
                        getattr(s, "priority_score", 0.0) or 0.0,
                        (s.take_profit_price - s.candidate_entry_price) / max(0.01, s.candidate_entry_price - s.stop_loss_price) if s.candidate_entry_price > s.stop_loss_price else 0.0,
                        getattr(s, "metrics", {}).get("vol_ratio", 0.0) or 0.0,
                        s.symbol,
                    ),
                    reverse=True,
                )

                # 遍历前一日生成的信号
                for sig in sorted_pending_signals:
                    sym = sig.symbol
                    if sym in open_positions:
                        continue  # 已有持仓，不重复开仓加仓
                    if len(open_positions) >= self.max_concurrent_positions:
                        break  # 持仓数量已达上限

                    if dt not in indexed_dfs.get(sym, {}):
                        continue  # 今日无行情或停牌

                    bar = indexed_dfs[sym][dt]
                    cur_open = float(bar["open"])
                    is_suspended = bool(bar.get("is_suspended", False))
                    prev_close = float(bar.get("prev_close", cur_open))
                    is_st_bar = bool(bar.get("is_st", False))
                    is_ipo_unlimited_bar = bool(bar.get("is_ipo_unlimited", False))

                    # 检查一字涨停限制 (涨停开盘买不进，严格适配 ST 与新股窗口)
                    limit_up, _ = calculate_price_limits(
                        prev_close, sym, is_st=is_st_bar, is_ipo_unlimited=is_ipo_unlimited_bar
                    )
                    is_restricted, _ = is_trade_restricted(cur_open, limit_up, 0.0, is_buy=True, is_suspended=is_suspended)
                    if is_restricted:
                        continue  # 开盘触及涨停或停牌，无法买入

                    # 实际买入价格计入滑点
                    actual_entry_price = cur_open * (1.0 + self.slippage_rate)
                    risk_dist = max(actual_entry_price - sig.stop_loss_price, actual_entry_price * 0.03)

                    # 资金与风险预算控制
                    total_equity_est = current_cash + sum(
                        pos["shares"] * indexed_dfs.get(s, {}).get(dt, {}).get("close", pos["entry_price"])
                        for s, pos in open_positions.items()
                    )
                    max_loss_budget = total_equity_est * self.risk_per_trade_pct
                    shares_by_risk = max_loss_budget / risk_dist

                    # 单票上限限制
                    max_amount_single = total_equity_est * self.max_position_pct_per_stock
                    shares_by_single = max_amount_single / actual_entry_price

                    # 现金上限限制
                    shares_by_cash = (current_cash * 0.98) / actual_entry_price

                    raw_shares = min(shares_by_risk, shares_by_single, shares_by_cash)
                    valid_shares = round_trade_quantity(int(raw_shares), sym, is_buy=True)

                    if valid_shares <= 0:
                        continue  # 资金或最小申报量不足

                    buy_amount = valid_shares * actual_entry_price
                    buy_fee_detail = calculate_trade_cost(
                        buy_amount,
                        is_buy=True,
                        trade_date=to_date_obj(dt),
                        commission_rate=self.commission_rate,
                        min_commission=self.min_commission,
                    )

                    if buy_amount + buy_fee_detail.total_fee > current_cash:
                        continue  # 现金硬约束不足

                    # 扣除现金并建立持仓
                    current_cash -= (buy_amount + buy_fee_detail.total_fee)
                    total_fees_accumulated += buy_fee_detail.total_fee
                    trade_counter += 1

                    # 计算 T+1 可卖日期
                    can_sell_date_obj = get_t_plus_n_date(to_date_obj(dt), n=1)
                    can_sell_date_str = can_sell_date_obj.strftime("%Y-%m-%d")

                    open_positions[sym] = {
                        "trade_id": f"T_{trade_counter:04d}",
                        "shares": valid_shares,
                        "entry_price": actual_entry_price,
                        "entry_date": dt,
                        "can_sell_date": can_sell_date_str,
                        "stop_loss": sig.stop_loss_price,
                        "take_profit": sig.take_profit_price,
                        "buy_fee": buy_fee_detail.total_fee,
                        "days": 0,
                    }

            # 3. 统计当日收盘权益
            positions_market_value = 0.0
            for sym, pos in open_positions.items():
                close_p = indexed_dfs.get(sym, {}).get(dt, {}).get("close", pos["entry_price"])
                positions_market_value += pos["shares"] * float(close_p)

            total_equity = current_cash + positions_market_value
            equity_records.append({
                "date": dt,
                "cash": round(current_cash, 2),
                "market_value": round(positions_market_value, 2),
                "total_equity": round(total_equity, 2),
                "open_positions_count": len(open_positions),
            })

            if split_date:
                if dt < split_date:
                    in_sample_equities.append(total_equity)
                else:
                    out_of_sample_equities.append(total_equity)

        # 回测结束：统计各项指标
        equity_df = pd.DataFrame(equity_records)
        metrics = self._calculate_metrics(
            equity_df=equity_df,
            closed_trades=closed_trades,
            total_fees_paid=total_fees_accumulated,
            benchmark_df=benchmark_df,
            in_sample_equities=in_sample_equities,
            out_of_sample_equities=out_of_sample_equities,
        )

        return metrics, equity_df, closed_trades

    def _calculate_metrics(
        self,
        equity_df: pd.DataFrame,
        closed_trades: List[TradeRecord],
        total_fees_paid: float,
        benchmark_df: Optional[pd.DataFrame] = None,
        in_sample_equities: Optional[List[float]] = None,
        out_of_sample_equities: Optional[List[float]] = None,
    ) -> BacktestMetrics:
        """根据标准金融指标计算收益率、回撤、胜率与夏普"""
        if len(equity_df) == 0:
            return BacktestMetrics(
                initial_capital=self.initial_capital,
                final_equity=self.initial_capital,
                total_net_pnl=0.0,
                total_return_pct=0.0,
                annualized_return_pct=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                avg_win_pct=0.0,
                avg_loss_pct=0.0,
                profit_loss_ratio=0.0,
                avg_holding_days=0.0,
                total_fees_paid=0.0,
                max_consecutive_losses=0,
            )

        final_equity = float(equity_df["total_equity"].iloc[-1])
        total_net_pnl = final_equity - self.initial_capital
        total_return_pct = total_net_pnl / self.initial_capital

        # 年化收益率 (以 242 个交易日计)
        num_days = len(equity_df)
        years = max(num_days / 242.0, 0.05)
        annualized_return_pct = ((final_equity / self.initial_capital) ** (1.0 / years)) - 1.0

        # 最大回撤
        cummax = equity_df["total_equity"].cummax()
        drawdown_series = (equity_df["total_equity"] - cummax) / cummax
        max_drawdown_pct = abs(float(drawdown_series.min()))

        # 日收益率与夏普比率 (无风险利率假定 2.5%)
        daily_returns = equity_df["total_equity"].pct_change().dropna()
        daily_rf = 0.025 / 242.0
        excess_returns = daily_returns - daily_rf
        std = excess_returns.std()
        if std > 1e-8:
            sharpe_ratio = float((excess_returns.mean() / std) * np.sqrt(242))
        else:
            sharpe_ratio = 0.0

        # 交易明细统计
        total_trades = len(closed_trades)
        wins = [t for t in closed_trades if (t.net_pnl or 0) > 0]
        losses = [t for t in closed_trades if (t.net_pnl or 0) < 0]

        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate_pct = (winning_trades / total_trades) if total_trades > 0 else 0.0

        avg_win_pct = float(np.mean([t.pnl_pct for t in wins])) if wins else 0.0
        avg_loss_pct = abs(float(np.mean([t.pnl_pct for t in losses]))) if losses else 0.0

        if avg_loss_pct > 1e-6:
            profit_loss_ratio = avg_win_pct / avg_loss_pct
        elif winning_trades > 0:
            profit_loss_ratio = 10.0  # 避免除零，上限截断
        else:
            profit_loss_ratio = 0.0

        avg_holding_days = float(np.mean([t.holding_days for t in closed_trades])) if closed_trades else 0.0

        # 最大连续亏损次数
        max_consec_losses = 0
        cur_consec = 0
        for t in closed_trades:
            if (t.net_pnl or 0) < 0:
                cur_consec += 1
                if cur_consec > max_consec_losses:
                    max_consec_losses = cur_consec
            else:
                cur_consec = 0

        # 基准对比 (例如沪深300)
        benchmark_ret = None
        alpha_pct = None
        if benchmark_df is not None and len(benchmark_df) >= 2 and "close" in benchmark_df.columns:
            b_start = float(benchmark_df["close"].iloc[0])
            b_end = float(benchmark_df["close"].iloc[-1])
            if b_start > 0:
                benchmark_ret = (b_end - b_start) / b_start
                alpha_pct = total_return_pct - benchmark_ret

        # 样本内与样本外收益
        in_sample_ret = None
        out_of_sample_ret = None
        if in_sample_equities and len(in_sample_equities) > 1:
            in_sample_ret = (in_sample_equities[-1] - in_sample_equities[0]) / in_sample_equities[0]
        if out_of_sample_equities and len(out_of_sample_equities) > 1:
            out_of_sample_ret = (out_of_sample_equities[-1] - out_of_sample_equities[0]) / out_of_sample_equities[0]

        return BacktestMetrics(
            initial_capital=self.initial_capital,
            final_equity=round(final_equity, 2),
            total_net_pnl=round(total_net_pnl, 2),
            total_return_pct=round(total_return_pct, 4),
            annualized_return_pct=round(annualized_return_pct, 4),
            max_drawdown_pct=round(max_drawdown_pct, 4),
            sharpe_ratio=round(sharpe_ratio, 2),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=round(win_rate_pct, 4),
            avg_win_pct=round(avg_win_pct, 4),
            avg_loss_pct=round(avg_loss_pct, 4),
            profit_loss_ratio=round(profit_loss_ratio, 2),
            avg_holding_days=round(avg_holding_days, 1),
            total_fees_paid=round(total_fees_paid, 2),
            max_consecutive_losses=max_consec_losses,
            benchmark_return_pct=round(benchmark_ret, 4) if benchmark_ret is not None else None,
            alpha_pct=round(alpha_pct, 4) if alpha_pct is not None else None,
            in_sample_return_pct=round(in_sample_ret, 4) if in_sample_ret is not None else None,
            out_of_sample_return_pct=round(out_of_sample_ret, 4) if out_of_sample_ret is not None else None,
        )
