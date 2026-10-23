"""
页面 2: 股票详情与波段分析 (Stock Detail & Swing Analysis Page)
包含：
1. 股票代码检索与板块交易规则信息展示 (最小申报量、申报递增单位、涨跌幅限制)
2. 交互式三合一技术分析图表 (K线 + 均线支撑 + 止损止盈参考线 + 成交量 + RSI)
3. 波段策略研判核心模块：
   - 趋势回调观察策略 vs 区间突破观察策略
   - “已满足条件”与“尚需等待条件”明确拆解
   - 严格止损参考价与其客观计算依据 (ATR / 波段低点)
   - 主要风险备忘与数据基准日期
4. 动态仓位计算与风控检查卡片 (依单笔风险预算测算建议股数)
5. 一键模拟开仓委托
"""

import streamlit as st
import pandas as pd

from core.paper_account import OrderDirection, PaperAccountManager
from core.risk_manager import RiskBudgetConfig, RiskManager
from core.rules import classify_symbol, get_board_rules
from core.strategies.range_breakout import RangeBreakoutStrategy
from core.strategies.trend_pullback import TrendPullbackStrategy
from data_provider.ai_advisor import AIAdvisor
from data_provider.manager import DataManager
from ui.charts import create_candlestick_chart
from ui.components import render_board_badge


def render_stock_detail_page(
    data_manager: DataManager,
    paper_manager: PaperAccountManager,
    risk_manager: RiskManager,
    ai_advisor: AIAdvisor,
):
    st.markdown("## 📈 股票详情与波段策略拆解")

    # 1. 标的选择与检索
    watchlist = data_manager.get_watchlist()
    watch_symbols = [f"{item['symbol']} - {item['name']}" for item in watchlist]

    col_s1, col_s2, col_s3 = st.columns([2.5, 2.5, 1.5])
    with col_s1:
        selected_from_watch = st.selectbox(
            "📌 从自选股中选择",
            options=["-- 请选择自选股票 --"] + watch_symbols,
            index=1 if len(watch_symbols) > 0 else 0,
        )
    with col_s2:
        custom_input = st.text_input("🔍 或直接输入 A 股代码", placeholder="输入 6 位代码，如 688981")
    with col_s3:
        strat_choice = st.selectbox("🎯 策略模型", ["趋势回调观察策略", "区间突破观察策略"])

    target_symbol = ""
    if custom_input.strip():
        target_symbol = custom_input.strip()
    elif selected_from_watch and not selected_from_watch.startswith("--"):
        target_symbol = selected_from_watch.split(" - ")[0].strip()
    elif len(watchlist) > 0:
        target_symbol = watchlist[0]["symbol"]
    else:
        target_symbol = "600519"

    stock_name = data_manager.get_stock_name(target_symbol)
    board_key, exchange, board_name = classify_symbol(target_symbol)
    rules = get_board_rules(target_symbol)

    # 2. 板块交易规则速查卡
    st.markdown(f"""
    <div style="background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 10px 16px; margin: 10px 0 16px 0;">
        <span style="font-size: 1.2rem; font-weight: bold; margin-right: 12px;">{stock_name} ({target_symbol})</span>
        {render_board_badge(board_key, board_name)}
        <span style="font-size: 0.84rem; color: #495057; margin-left: 12px;">
            交易所规则: <strong>买入起点 {rules.min_buy_qty} 股</strong> (递增单位 {rules.qty_step} 股) | 
            涨跌幅限制: <strong>±{rules.price_limit_ratio*100:.0f}%</strong> (ST为 ±{rules.st_price_limit_ratio*100:.0f}%) | 
            交易制度: <strong>T+1 卖出</strong> (当日买入次日及之后方可卖出)
        </span>
    </div>
    """, unsafe_allow_html=True)

    # 3. 加载日线数据与指标
    with st.spinner(f"正在调取 {stock_name} 历史日线与计算波段技术指标..."):
        df, source_desc = data_manager.get_daily_bars(target_symbol)

    if len(df) == 0:
        st.error(f"未能获取到标的 {target_symbol} 的历史行情，可能原因：代码不正确、非交易时间网络超时或未上市。")
        return

    latest_row = df.iloc[-1]
    latest_close = float(latest_row["close"])
    latest_date = str(latest_row["date"])[:10]

    # 4. 初始化策略并评估
    if strat_choice == "趋势回调观察策略":
        strategy = TrendPullbackStrategy()
    else:
        strategy = RangeBreakoutStrategy()

    signal = strategy.evaluate_latest(df, target_symbol)

    # 5. 渲染 Plotly K线与交互指标图
    fig = create_candlestick_chart(
        df=df,
        symbol=target_symbol,
        name=stock_name,
        entry_price=signal.candidate_entry_price if signal.is_actionable else None,
        stop_loss_price=signal.stop_loss_price,
        take_profit_price=signal.take_profit_price,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(f"📊 行情数据来源: {source_desc} | 数据截止日期: {latest_date} | 单位: 价格(元), 成交量(股)")

    # 6. 策略研判细化拆解面板
    st.markdown("---")
    st.markdown(f"### 🎯 【{strategy.name}】综合研判")

    col_sig1, col_sig2 = st.columns([1.8, 1.2])

    with col_sig1:
        # 信号结论状态
        if signal.is_actionable:
            st.success(f"🔥 **候选入场条件全部触发！** (建议入场参考价: ¥{signal.candidate_entry_price:.2f})")
        else:
            st.warning(f"⏳ **当前暂无合适买入机会 / 正在观察中** (尚需等待 {len(signal.conditions_pending)} 项条件成熟)")

        # 已满足条件
        st.markdown("#### ✅ 已满足的技术条件:")
        if signal.conditions_met:
            for met in signal.conditions_met:
                st.markdown(f"<div class='condition-box-met'>✔ {met}</div>", unsafe_allow_html=True)
        else:
            st.write("暂无核心条件满足")

        # 待观察条件
        st.markdown("#### ⏳ 尚需等待的条件:")
        if signal.conditions_pending:
            for pen in signal.conditions_pending:
                st.markdown(f"<div class='condition-box-pending'>⏳ {pen}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='condition-box-met'>全部入场条件均已满足</div>", unsafe_allow_html=True)

        # 核心风险清单
        st.markdown("#### ⚠️ 主要风险提示:")
        for rk in signal.risks:
            st.markdown(f"<div class='condition-box-risk'>⚠ {rk}</div>", unsafe_allow_html=True)

    with col_sig2:
        st.markdown("#### 🛡️ 止损与目标位测算")
        st.metric("建议入场参考价", f"¥{signal.candidate_entry_price:.2f}" if signal.candidate_entry_price > 0 else f"¥{latest_close:.2f}")

        stop_diff = (signal.candidate_entry_price - signal.stop_loss_price) if signal.candidate_entry_price > 0 else (latest_close - signal.stop_loss_price)
        stop_pct = (stop_diff / latest_close * 100.0) if latest_close > 0 else 0.0
        st.metric("建议止损参考价", f"¥{signal.stop_loss_price:.2f}", f"-{stop_pct:.1f}% 风险缓冲", delta_color="inverse")
        st.caption(f"**止损计算依据**: {signal.stop_loss_rationale}")

        st.metric("目标止盈位 (盈亏比2.5:1)", f"¥{signal.take_profit_price:.2f}")

        # 动态仓位测算
        st.markdown("---")
        st.markdown("#### 💼 模拟仓位风控测算")
        account_summary = paper_manager.get_account_summary()
        current_cash = account_summary["cash"]
        existing_positions = {p.symbol: {"market_val": p.market_value, "industry": "其他"} for p in account_summary["positions"]}

        proposal = risk_manager.calculate_position_size(
            symbol=target_symbol,
            entry_price=signal.candidate_entry_price or latest_close,
            stop_loss_price=signal.stop_loss_price,
            current_cash=current_cash,
            current_positions=existing_positions,
        )

        st.markdown(f"""
        - 建议委托数量: **{proposal.recommended_shares} 股** (经板块整手规则规范)
        - 预计占用资金: **¥{proposal.recommended_amount:.2f}** (占本金 {proposal.position_pct_of_capital*100:.1f}%)
        - 止损触发预估损失: **¥{proposal.estimated_loss_at_stop:.2f}** (含双边交易税费)
        - 预估买卖双边手续费: **¥{proposal.fee_estimate:.2f}**
        """)

        # 一键模拟下单
        if proposal.recommended_shares > 0:
            if st.button("🚀 按建议仓位执行模拟买入", use_container_width=True, type="primary"):
                order = paper_manager.place_order(
                    symbol=target_symbol,
                    direction=OrderDirection.BUY,
                    shares=proposal.recommended_shares,
                    price=proposal.entry_price,
                    strategy_name=strategy.name,
                    reason=f"【{strategy.name}】候选信号确认",
                )
                if order.status == "FILLED":
                    st.success(f"模拟买入已成交: {target_symbol} 共 {order.filled_shares} 股，成交价 ¥{order.filled_price:.2f}")
                else:
                    st.warning(f"模拟委托未成交: {order.reason}")
        else:
            st.info("因资金、申报门槛或风控限制，当前建议股数为 0。")

    # 7. 可选 AI 解构研判卡片
    st.markdown("---")
    with st.expander("🤖 可选 AI 智能解构与风险备忘 (点击展开)", expanded=False):
        commentary = ai_advisor.generate_stock_commentary(
            symbol=target_symbol,
            name=stock_name,
            signal_data={
                "strategy_name": strategy.name,
                "is_actionable": signal.is_actionable,
                "candidate_entry_price": signal.candidate_entry_price,
                "stop_loss_price": signal.stop_loss_price,
                "stop_loss_rationale": signal.stop_loss_rationale,
                "take_profit_price": signal.take_profit_price,
                "conditions_met": signal.conditions_met,
                "conditions_pending": signal.conditions_pending,
                "risks": signal.risks,
                "date": latest_date,
            },
            indicators_snapshot=signal.metrics,
        )
        st.markdown(commentary["content"])
        st.caption(f"🔍 研判引擎: {commentary['model_name']} | 研判时间: {commentary['generated_at']} | 免责声明: {commentary['disclaimer']}")
