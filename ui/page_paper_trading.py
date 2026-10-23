"""
页面 5: 模拟交易与复盘记账 (Paper Trading & Journal Page)
特性：
1. 真实模拟账户资产记账 (现金、持仓市值、总资产、收益率)
2. 在仓持仓监控与 T+1 可卖额度展示
3. 模拟买入/卖出委托与板块整手规则强制规整
4. 订单状态历史跟踪 (PENDING, FILLED, UNFILLED, CANCELLED)
5. 历史交易明细、收益复盘与 CSV 导出
6. 模拟账户一键重置
"""

from datetime import datetime
import streamlit as st
import pandas as pd

from core.paper_account import OrderDirection, PaperAccountManager
from core.rules import classify_symbol, get_board_rules
from data_provider.manager import DataManager
from ui.components import render_board_badge


def render_paper_trading_page(data_manager: DataManager, paper_manager: PaperAccountManager):
    st.markdown("## 💼 模拟交易与复盘账本")

    # 1. 顶部总览卡片
    # 查询当前持仓的最新价格以计算最新市值
    raw_summary = paper_manager.get_account_summary()
    current_prices = {}
    for pos in raw_summary["positions"]:
        quote = data_manager.get_spot_quote(pos.symbol)
        if quote:
            current_prices[pos.symbol] = quote.price
        else:
            df, _ = data_manager.get_daily_bars(pos.symbol, use_cache=True)
            if len(df) > 0:
                current_prices[pos.symbol] = float(df["close"].iloc[-1])

    summary = paper_manager.get_account_summary(current_prices)

    st.markdown("""
    <div class="sim-banner">
        <strong>⚠️ 模拟账户声明:</strong> 本模块为策略演练账本，所有资金均为虚拟模拟资金，用于验证买卖纪律、T+1 规则和止损止盈执行度，杜绝冒充真实券商账户。
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("初始模拟本金", f"¥{summary['initial_capital']:,.2f}")
    c2.metric("可用现金", f"¥{summary['cash']:,.2f}")
    c3.metric("持仓总市值", f"¥{summary['market_value']:,.2f}")

    pnl_delta = f"{summary['return_pct']*100:.2f}%"
    pnl_color = "normal" if summary["net_pnl"] >= 0 else "inverse"
    c4.metric("总资产", f"¥{summary['total_equity']:,.2f}", pnl_delta, delta_color=pnl_color)
    c5.metric("当前在仓标的数", f"{summary['positions_count']} 只")

    # 2. 当前持仓列表
    st.markdown("### 📦 当前持仓监控 (执行严格 T+1 可卖额度)")
    if summary["positions"]:
        pos_list = []
        for p in summary["positions"]:
            name = data_manager.get_stock_name(p.symbol)
            board_key, _, board_name = classify_symbol(p.symbol)
            pnl_pct_str = f"{p.unrealized_pnl_pct*100:+.2f}%"
            pos_list.append({
                "代码": p.symbol,
                "名称": name,
                "板块": board_name,
                "board_key": board_key,
                "持股数量": p.shares,
                "T+1可卖股数": p.available_shares,
                "持仓均价": f"¥{p.avg_cost_price:.2f}",
                "最新现价": f"¥{p.last_price:.2f}",
                "最新市值": f"¥{p.market_value:,.2f}",
                "浮动盈亏": f"¥{p.unrealized_pnl:,.2f} ({pnl_pct_str})",
                "初次建仓日": p.first_buy_date,
            })

        for p_row in pos_list:
            cols = st.columns([1.2, 1.5, 1.2, 1.0, 1.0, 1.2, 1.2, 1.5, 1.5, 1.2])
            cols[0].markdown(f"`{p_row['代码']}`")
            cols[1].markdown(f"**{p_row['名称']}**")
            cols[2].markdown(render_board_badge(p_row["board_key"], p_row["板块"]), unsafe_allow_html=True)
            cols[3].markdown(f"{p_row['持股数量']}")
            cols[4].markdown(f"**{p_row['T+1可卖股数']}**")
            cols[5].markdown(p_row["持仓均价"])
            cols[6].markdown(p_row["最新现价"])
            cols[7].markdown(p_row["最新市值"])
            cols[8].markdown(p_row["浮动盈亏"])

            # 快捷平仓按钮
            if cols[9].button("平仓卖出", key=f"sell_pos_{p_row['代码']}"):
                st.session_state["sell_target_symbol"] = p_row["代码"]
                st.session_state["sell_max_shares"] = p_row["T+1可卖股数"]
    else:
        st.info("当前暂无持仓标的。可在下方进行手动模拟买入或在【股票详情】页由策略建议一键建仓。")

    # 3. 手动模拟委托下单区
    st.markdown("---")
    st.markdown("### 📝 模拟委托申报")
    with st.form("trade_order_form"):
        f1, f2, f3, f4, f5 = st.columns([1.5, 1.5, 1.5, 1.5, 2.5])
        with f1:
            sym_default = st.session_state.get("sell_target_symbol", "")
            target_sym = st.text_input("股票代码", value=sym_default, placeholder="如 600519")
        with f2:
            direction_str = st.selectbox("交易方向", ["买入开仓 (BUY)", "卖出平仓 (SELL)"])
        with f3:
            shares_input = st.number_input("委托股数", min_value=1, value=100, step=100)
        with f4:
            price_input = st.number_input("委托价格 (元)", min_value=0.01, value=10.0, step=0.1, format="%.2f")
        with f5:
            reason_input = st.text_input("交易依据 / 复盘笔记", value="波段交易规则触发执行")

        submit_order = st.form_submit_button("📤 提交模拟委托单", type="primary", use_container_width=True)

        if submit_order:
            if not target_sym.strip():
                st.error("请输入有效的股票代码")
            else:
                direction = OrderDirection.BUY if "BUY" in direction_str else OrderDirection.SELL
                order = paper_manager.place_order(
                    symbol=target_sym.strip(),
                    direction=direction,
                    shares=int(shares_input),
                    price=float(price_input),
                    reason=reason_input,
                )
                if order.status == "FILLED":
                    st.success(f"委托成功完全成交！{order.direction} {order.symbol} 共 {order.filled_shares} 股，成交均价 ¥{order.filled_price:.2f}，扣费 ¥{order.fee:.2f}")
                    st.rerun()
                elif order.status == "UNFILLED":
                    st.error(f"委托未成交: {order.reason}")
                else:
                    st.warning(f"委托状态: {order.status} ({order.reason})")

    # 4. 委托历史与复盘明细流水
    st.markdown("---")
    tab_orders, tab_history = st.tabs(["📋 委托订单记录", "📑 交易明细与复盘流水"])

    with tab_orders:
        orders_df = paper_manager.get_orders_df()
        if len(orders_df) > 0:
            st.dataframe(orders_df, use_container_width=True)
        else:
            st.info("暂无历史委托记录。")

    with tab_history:
        history_df = paper_manager.get_trade_history_df()
        if len(history_df) > 0:
            st.dataframe(history_df, use_container_width=True)
            csv_data = history_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 导出模拟交易流水为 CSV 文件",
                data=csv_data,
                file_name=f"paper_trade_journal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )
        else:
            st.info("暂无成交历史流水。")

    # 5. 危险操作区 (重置账户)
    st.markdown("---")
    with st.expander("⚠️ 账户重置管理 (清空模拟持仓与资金记录)"):
        st.caption("重置后将清除全部模拟持仓、委托历史与交易日志，恢复为初始本金。")
        col_r1, col_r2 = st.columns([2, 1])
        with col_r1:
            new_init_cap = st.number_input("重设初始本金 (元)", value=100000.0, step=10000.0)
        with col_r2:
            st.write("")
            st.write("")
            if st.button("🗑️ 确认重置模拟账户", type="secondary"):
                paper_manager.reset_account(new_init_cap)
                st.success("模拟账户已成功重置！")
                st.rerun()
