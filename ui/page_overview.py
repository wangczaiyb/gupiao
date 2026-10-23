"""
页面 1: 市场总览与自选机会 (Overview Page)
包含：
- A 股市场状态与真实交易日指示
- 自选股实时监控与波段信号状态雷达
- 自选股代码快速查询、添加与移除
- 数据源与更新时间提示
- 严谨的风险揭示与模拟资金标示
"""

from datetime import date, datetime
import streamlit as st
import pandas as pd

from core.calendar import is_trading_day, get_next_trading_day
from core.rules import classify_symbol
from core.strategies.trend_pullback import TrendPullbackStrategy
from core.strategies.range_breakout import RangeBreakoutStrategy
from data_provider.manager import DataManager
from ui.components import render_board_badge


def render_overview_page(data_manager: DataManager):
    st.markdown("## 📊 A 股波段交易辅助系统 · 市场总览")

    # 1. 顶部免责与模式横幅
    today_obj = date.today()
    is_open = is_trading_day(today_obj)
    status_text = "🟢 今日为 A 股正式交易日" if is_open else f"⚪ 今日休市 (下一交易日: {get_next_trading_day(today_obj)})"

    st.markdown(f"""
    <div class="sim-banner">
        <strong>💡 运行提示:</strong> {status_text} | 当前系统运行于【波段决策辅助与模拟演算模式】，所有资金标示均为模拟资金，不接入券商实盘下单，严禁将历史回测与量化评分视为确定性收益保证。
    </div>
    """, unsafe_allow_html=True)

    # 2. 自选股操作栏
    col_add1, col_add2, col_add3 = st.columns([2, 3, 1.2])
    with col_add1:
        new_symbol = st.text_input("🔍 输入股票代码查询/添加", placeholder="如: 600519 或 300750 或 920211", key="add_sym_input")
    with col_add2:
        new_note = st.text_input("📝 关注备注 (可选)", placeholder="如: 观察20日线回踩支撑", key="add_note_input")
    with col_add3:
        st.write("")
        st.write("")
        if st.button("➕ 添加到自选", use_container_width=True):
            if new_symbol:
                clean_sym = new_symbol.strip()
                name = data_manager.get_stock_name(clean_sym)
                success = data_manager.add_to_watchlist(clean_sym, name, new_note)
                if success:
                    st.success(f"已成功添加: {name} ({clean_sym})")
                    st.rerun()
                else:
                    st.error("请输入有效的 A 股数字代码 (支持沪深北主板、创业板、科创板与北交所)")

    # 3. 自选股列表与波段信号概览
    watchlist = data_manager.get_watchlist()
    st.markdown(f"### 📋 自选股监控池 ({len(watchlist)} 只)")

    if not watchlist:
        st.info("暂无自选股，请在上方输入代码添加。")
        return

    # 初始化策略用于快速扫描最新信号
    trend_strat = TrendPullbackStrategy()
    breakout_strat = RangeBreakoutStrategy()

    rows_data = []
    for item in watchlist:
        sym = item["symbol"]
        name = item["name"]
        board_key = item["board_key"]
        board_name = item["board_name"]

        # 获取行情与指标
        df, source_desc = data_manager.get_daily_bars(sym, use_cache=True)
        latest_price = 0.0
        pct_chg = 0.0
        signal_status = "数据加载中"
        signal_type = "NONE"
        latest_date = "-"

        if len(df) > 0:
            latest_row = df.iloc[-1]
            latest_price = float(latest_row.get("close", 0.0))
            pct_chg = float(latest_row.get("pct_chg", 0.0))
            latest_date = str(latest_row.get("date", "-"))[:10]

            # 评估两种策略
            sig_trend = trend_strat.evaluate_latest(df, sym)
            sig_break = breakout_strat.evaluate_latest(df, sym)

            if sig_trend.is_actionable:
                signal_status = "🎯 触发趋势回调买点"
                signal_type = "BUY"
            elif sig_break.is_actionable:
                signal_status = "🚀 触发区间突破买点"
                signal_type = "BUY"
            else:
                p_trend = len(sig_trend.conditions_pending)
                p_break = len(sig_break.conditions_pending)
                signal_status = f"⏳ 观察中 (待满足条件: 回调{p_trend}项/突破{p_break}项)"

        rows_data.append({
            "代码": sym,
            "名称": name,
            "板块": board_name,
            "board_key": board_key,
            "最新价": latest_price,
            "涨跌幅": pct_chg,
            "行情日期": latest_date,
            "波段信号": signal_status,
            "signal_type": signal_type,
            "备注": item["notes"],
        })

    # 渲染自选股监控表格
    cols_header = st.columns([1.2, 1.5, 1.2, 1.2, 1.2, 1.5, 2.5, 1.0])
    cols_header[0].markdown("**代码**")
    cols_header[1].markdown("**名称**")
    cols_header[2].markdown("**板块**")
    cols_header[3].markdown("**最新价**")
    cols_header[4].markdown("**涨跌幅**")
    cols_header[5].markdown("**最新行情日**")
    cols_header[6].markdown("**波段策略研判**")
    cols_header[7].markdown("**操作**")

    st.markdown("<hr style='margin: 4px 0 12px 0;'>", unsafe_allow_html=True)

    for r in rows_data:
        c = st.columns([1.2, 1.5, 1.2, 1.2, 1.2, 1.5, 2.5, 1.0])
        c[0].markdown(f"`{r['代码']}`")
        c[1].markdown(f"**{r['名称']}**")
        c[2].markdown(render_board_badge(r["board_key"], r["板块"]), unsafe_allow_html=True)

        # 价格与涨跌幅颜色
        color_class = "val-up" if r["涨跌幅"] > 0 else ("val-down" if r["涨跌幅"] < 0 else "")
        sign = "+" if r["涨跌幅"] > 0 else ""
        c[3].markdown(f"<span class='{color_class}'>¥{r['最新价']:.2f}</span>", unsafe_allow_html=True)
        c[4].markdown(f"<span class='{color_class}'>{sign}{r['涨跌幅']:.2f}%</span>", unsafe_allow_html=True)
        c[5].markdown(f"<small>{r['行情日期']}</small>", unsafe_allow_html=True)

        if r["signal_type"] == "BUY":
            c[6].markdown(f"<span style='color: #cf1322; font-weight: bold;'>{r['波段信号']}</span>", unsafe_allow_html=True)
        else:
            c[6].markdown(f"<span style='color: #595959;'>{r['波段信号']}</span>", unsafe_allow_html=True)

        if c[7].button("🗑️", key=f"del_{r['代码']}", help="从自选股移除"):
            data_manager.remove_from_watchlist(r["代码"])
            st.rerun()

    # 4. 底部快捷操作与数据更新状态
    st.markdown("---")
    foot_col1, foot_col2 = st.columns([3, 1])
    with foot_col1:
        st.markdown(
            "💡 **提示**: 点击左侧导航栏的【📈 股票详情与波段分析】可查看完整交互式 K 线、条件拆解与入场/止损测算；点击【🔍 全市场策略筛选】可全量扫描潜在交易机会。"
        )
    with foot_col2:
        if st.button("🔄 刷新全部自选行情", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
