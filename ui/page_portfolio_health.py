"""
页面 7: 智能持仓体检与风控诊断 (Portfolio Health Page)
特性:
1. 支持手动录入或 CSV 批量导入持仓 (股票代码、成本价、持仓股数、买入日期)
2. 全维量化诊断: 单票盈亏比、走势结构、关键支撑位、阻力位与移动止损点
3. 组合层面风险透视: 单票集中度超标、行业暴露集中度、大幅回撤报警
4. 结合规则引擎与可选 AI Agent 生成客观复盘备忘
"""

import io
import streamlit as st
import pandas as pd
from core.portfolio_health import HoldingItem, PortfolioHealthAnalyzer
from data_provider.ai_advisor import AIAdvisor
from data_provider.manager import DataManager
from ui.components import render_board_badge


def render_portfolio_health_page(data_manager: DataManager, ai_advisor: AIAdvisor):
    st.markdown("## 🩺 智能持仓体检与量化风控诊断")
    st.caption("真实持仓客观诊断 · 均线多空结构 · 关键支撑阻力 · 组合集中度与移动止损建议")

    analyzer = PortfolioHealthAnalyzer(data_manager)

    tab_input, tab_report = st.tabs(["📥 持仓录入 / 导入", "📊 体检诊断报告"])

    # 初始化持仓 session_state
    if "user_holdings" not in st.session_state:
        st.session_state["user_holdings"] = [
            HoldingItem(symbol="600519", cost_price=1680.0, shares=100, buy_date="2024-03-01", notes="核心底仓"),
            HoldingItem(symbol="300750", cost_price=210.0, shares=200, buy_date="2024-04-15", notes="新能源赛道"),
            HoldingItem(symbol="000001", cost_price=11.2, shares=1000, buy_date="2024-05-10", notes="金融防御"),
        ]

    with tab_input:
        col_in1, col_in2 = st.columns([1, 1])

        with col_in1:
            st.markdown("### ➕ 手动添加持仓")
            with st.form("add_holding_form"):
                in_sym = st.text_input("股票代码 (6位数字)", value="688981", max_chars=6)
                in_cost = st.number_input("持仓成本价 (元)", value=52.5, min_value=0.01, step=0.1)
                in_shares = st.number_input("持仓数量 (股)", value=200, min_value=1, step=100)
                in_date = st.date_input("买入日期")
                in_note = st.text_input("备注标签", value="半导体龙头")
                if st.form_submit_button("添加至体检清单", type="primary"):
                    if in_sym and in_cost > 0 and in_shares > 0:
                        st.session_state["user_holdings"].append(
                            HoldingItem(
                                symbol=in_sym.strip(),
                                cost_price=float(in_cost),
                                shares=int(in_shares),
                                buy_date=str(in_date),
                                notes=in_note,
                            )
                        )
                        st.success(f"已成功添加标的 {in_sym} 到体检清单！")
                        st.rerun()

        with col_in2:
            st.markdown("### 📁 CSV 批量导入持仓")
            uploaded_file = st.file_uploader("上传持仓 CSV 文件 (包含代码、成本价、股数)", type=["csv"])
            if uploaded_file is not None:
                try:
                    content = uploaded_file.getvalue().decode("utf-8")
                    parsed = analyzer.parse_holdings_csv(content)
                    if st.button("确认导入此 CSV 持仓", type="primary"):
                        st.session_state["user_holdings"] = parsed
                        st.success(f"成功导入 {len(parsed)} 只持仓标的！")
                        st.rerun()
                except Exception as e:
                    st.error(f"解析 CSV 失败: {e}")

            st.caption("CSV 示例格式: `symbol,cost,shares,buy_date`")

        st.markdown("---")
        st.markdown("### 📋 当前体检清单")
        if st.session_state["user_holdings"]:
            records = []
            for idx, h in enumerate(st.session_state["user_holdings"]):
                name = data_manager.get_stock_name(h.symbol)
                records.append({
                    "序号": idx + 1,
                    "代码": h.symbol,
                    "名称": name,
                    "成本价(元)": f"{h.cost_price:.2f}",
                    "持股数": h.shares,
                    "成本金额(元)": f"{h.cost_price * h.shares:.2f}",
                    "买入日期": h.buy_date,
                    "备注": h.notes,
                })
            st.dataframe(pd.DataFrame(records), use_container_width=True)
            if st.button("🗑️ 清空当前持仓清单"):
                st.session_state["user_holdings"] = []
                st.rerun()
        else:
            st.info("持仓清单为空，请在上方添加或上传持仓。")

    with tab_report:
        if not st.session_state["user_holdings"]:
            st.warning("请先在【持仓录入】标签页添加或导入持仓数据。")
            return

        with st.spinner("正在逐标的获取最新行情并计算量化健康度..."):
            summary = analyzer.analyze_portfolio(st.session_state["user_holdings"])

        # 顶部组合级 KPI 卡片
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("组合总市值", f"{summary.total_market_value:,.2f} 元", f"总成本 {summary.total_cost:,.2f} 元")
        c1_delta = f"{summary.total_pnl_pct*100:+.2f}%"
        c2.metric("浮动总盈亏", f"{summary.total_unrealized_pnl:+,.2f} 元", c1_delta)
        c3.metric("持仓标的数", f"{summary.positions_count} 只", f"第一重仓 {summary.top_stock_weight_pct:.1f}%")
        
        status_color = "🟢" if summary.overall_health_score >= 80 else ("🟡" if summary.overall_health_score >= 50 else "🔴")
        c4.metric("综合健康评分", f"{status_color} {summary.overall_health_score:.1f} / 100", f"风控等级: {summary.overall_risk_rating}")

        # 核心预警横幅
        if summary.system_alerts:
            for alert in summary.system_alerts:
                st.warning(alert)
        else:
            st.success("✅ 组合整体结构健康，未触发高风险集中度或破位报警。")

        st.markdown("### 🔍 各持仓标的深度体检明细")
        pos_table = []
        for p in summary.detailed_positions:
            pos_table.append({
                "代码": p.symbol,
                "标的名称": p.name,
                "板块": p.board_name,
                "成本价": f"{p.cost_price:.2f}",
                "最新价": f"{p.current_price:.2f}",
                "持股数": p.shares,
                "浮动盈亏": f"{p.unrealized_pnl:+.2f}",
                "盈亏比例": f"{p.pnl_pct*100:+.2f}%",
                "趋势结构": p.trend_status,
                "近期支撑位": f"{p.support_level:.2f}",
                "近期阻力位": f"{p.resistance_level:.2f}",
                "建议移动止损": f"{p.suggested_stop_loss:.2f}",
                "风险等级": p.risk_level,
                "建议动作": p.action_advice,
            })
        st.dataframe(pd.DataFrame(pos_table), use_container_width=True)

        st.markdown("---")
        st.markdown("### 🤖 AI Agent 组合风控深度研判")
        ai_col1, ai_col2 = st.columns([3, 1])
        with ai_col1:
            st.caption("基于上述量化可验证事实，调用智能研判模块生成客观交易风控复盘备忘")
        with ai_col2:
            run_ai = st.button("生成 AI 体检备忘录", type="primary", use_container_width=True)

        if run_ai:
            with st.spinner("AI 正在严密结合规则事实生成风控备忘..."):
                commentary = ai_advisor.generate_portfolio_health_commentary(summary)
                st.markdown(commentary["content"])
                st.caption(f"ℹ️ {commentary['disclaimer']} | 模型: {commentary['model_name']} | 时间: {commentary['generated_at']}")
