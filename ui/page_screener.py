"""
页面 3: 智能选股与全市场波段机会扫描 (Screener Page)
参考 AlphaSift 架构特性：
1. 分层发现与确定性评分 (Certainty Score): 因子标准化与多策略加权综合排序
2. 动态真实股票池: 告别硬编码假市场，支持自选股、沪深300、精选池与全市场动态证券目录
3. 硬性风险前置过滤: 严格排除 ST、*ST、退市、停牌及次新炒作
4. 明确展示入场条件、已满足事实、尚缺条件、止损依据及失效离场红线
5. 支持一键加入自选股雷达
"""

import streamlit as st
import pandas as pd

from core.factors import compute_stock_factors
from core.strategies.range_breakout import RangeBreakoutStrategy
from core.strategies.rs_momentum import RSMomentumStrategy
from core.strategies.trend_pullback import TrendPullbackStrategy
from core.strategies.volatility_contraction import VolatilityContractionStrategy
from data_provider.manager import DataManager
from ui.components import render_board_badge


def render_screener_page(data_manager: DataManager):
    st.markdown("## 🔍 智能波段选股与机会扫描")
    st.caption("AlphaSift 分层发现机制 · 确定性综合评分 · 严格因果事实拆解 · 真实动态证券池")

    # 1. 扫描与筛选条件配置
    with st.expander("⚙️ 股票池与筛选参数配置", expanded=True):
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("**1. 标的板块范围选择**")
            inc_sh = st.checkbox("沪市主板 (600/601/603/605)", value=True)
            inc_sz = st.checkbox("深市主板 (000/001/002)", value=True)
            inc_chinext = st.checkbox("创业板 (300/301)", value=True)
            inc_star = st.checkbox("科创板 (688)", value=True)
            inc_bse = st.checkbox("北交所 (920/83/87)", value=True)

        with col_c2:
            st.markdown("**2. 风险与流动性过滤**")
            exclude_st = st.checkbox("排除 ST 与 *ST 风险警示股", value=True)
            exclude_delist = st.checkbox("排除退市整理期股票", value=True)
            exclude_susp = st.checkbox("排除停牌股票", value=True)
            min_days = st.slider("新股上市最短交易日数 (过滤次新炒作)", min_value=0, max_value=250, value=60, step=10)

        st.markdown("**3. 策略模型与扫描范围**")
        col_m1, col_m2 = st.columns([2, 2])
        with col_m1:
            strat_name = st.selectbox(
                "选择波段策略模型",
                [
                    "趋势回调观察策略 (Trend Pullback)",
                    "区间突破观察策略 (Range Breakout)",
                    "相对强度动量策略 (RS Momentum)",
                    "波动收缩突破策略 (VCP Breakout)",
                ],
            )
        with col_m2:
            scan_scope = st.selectbox(
                "扫描股票池范围",
                [
                    "自选股清单 (极速)",
                    "沪深300指数核心池 (快速)",
                    "精选沪深北代表池 (中速)",
                    "沪深北全市场动态证券池 (深度扫描)",
                ],
            )

    # 准备目标股票池
    boards_selected = []
    if inc_sh: boards_selected.append("SH_MAIN")
    if inc_sz: boards_selected.append("SZ_MAIN")
    if inc_chinext: boards_selected.append("CHINEXT")
    if inc_star: boards_selected.append("STAR")
    if inc_bse: boards_selected.append("BSE")

    # 触发扫描按钮
    if st.button("🚀 开始执行全流程扫描", type="primary", use_container_width=True):
        scope_key = "WATCHLIST"
        if "沪深300" in scan_scope:
            scope_key = "INDEX_300"
        elif "全市场" in scan_scope:
            scope_key = "ALL"
        else:
            scope_key = "CORE"

        valid_profiles = data_manager.get_market_universe(
            scope=scope_key,
            allowed_boards=boards_selected,
            exclude_st=exclude_st,
            exclude_delisting=exclude_delist,
            exclude_suspended=exclude_susp,
            min_listing_days=min_days,
        )

        st.info(f"经过板块及硬风控规则筛选，共有 **{len(valid_profiles)}** 只真实合规标的进入策略扫描执行链路...")

        # 实例化策略
        if "趋势回调" in strat_name:
            strategy = TrendPullbackStrategy()
        elif "区间突破" in strat_name:
            strategy = RangeBreakoutStrategy()
        elif "相对强度" in strat_name:
            strategy = RSMomentumStrategy()
        else:
            strategy = VolatilityContractionStrategy()

        progress_bar = st.progress(0)
        status_text = st.empty()

        results = []
        for idx, p in enumerate(valid_profiles):
            status_text.text(f"正在扫描 ({idx+1}/{len(valid_profiles)}): {p.symbol} - {p.name} ...")
            progress_bar.progress((idx + 1) / len(valid_profiles))

            df, _ = data_manager.get_daily_bars(p.symbol, use_cache=True)
            if len(df) >= 30:
                sig = strategy.evaluate_latest(df, p.symbol)
                latest_p = float(df["close"].iloc[-1])
                factors = compute_stock_factors(df, p.symbol)
                certainty = factors.certainty_score if factors else getattr(sig, "priority_score", 50.0)

                results.append({
                    "symbol": p.symbol,
                    "name": p.name,
                    "board_key": p.board_key,
                    "board_name": p.board_name,
                    "latest_price": latest_p,
                    "signal_type": sig.signal_type.value,
                    "is_actionable": sig.is_actionable,
                    "certainty_score": certainty,
                    "entry_price": sig.candidate_entry_price,
                    "stop_loss": sig.stop_loss_price,
                    "take_profit": sig.take_profit_price,
                    "stop_rationale": sig.stop_loss_rationale,
                    "met_count": len(sig.conditions_met),
                    "pending_count": len(sig.conditions_pending),
                    "met_details": "; ".join(sig.conditions_met[:3]),
                    "pending_details": "; ".join(sig.conditions_pending[:2]),
                    "risks": sig.risks,
                })

        progress_bar.empty()
        status_text.empty()

        # 按确定性评分降序排列
        results = sorted(results, key=lambda r: (r["is_actionable"], r["certainty_score"]), reverse=True)

        actionable_results = [r for r in results if r["is_actionable"]]
        pending_results = [r for r in results if not r["is_actionable"]]

        st.markdown(f"### 🎯 扫描结果汇总: 发现 **{len(actionable_results)}** 只候选买点标的")

        if actionable_results:
            st.success("以下标的已完全满足当前波段策略入场条件，按 AlphaSift 确定性评分优先推荐：")
            for rank_idx, r in enumerate(actionable_results):
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([1.5, 1.2, 1.2, 2.5, 1.2])
                    score_badge = f"🔥 确定性: **{r['certainty_score']:.1f}** 分"
                    c1.markdown(f"**#{rank_idx+1} {r['name']}** (`{r['symbol']}`)<br>{score_badge}", unsafe_allow_html=True)
                    c2.markdown(render_board_badge(r["board_key"], r["board_name"]), unsafe_allow_html=True)
                    c3.markdown(f"现价: **¥{r['latest_price']:.2f}**")
                    c4.markdown(f"入场参考: ¥{r['entry_price']:.2f} | 止损: **¥{r['stop_loss']:.2f}** | 止盈: **¥{r['take_profit']:.2f}**<br><small style='color: gray;'>依据: {r['stop_rationale']}</small>", unsafe_allow_html=True)
                    if c5.button("➕ 加入自选", key=f"add_scan_{r['symbol']}"):
                        data_manager.add_to_watchlist(r["symbol"], r["name"], f"【{strat_name.split('(')[0].strip()}】评分:{r['certainty_score']:.0f}")
                        st.success(f"已加入自选: {r['name']}")
                st.markdown("<hr style='margin: 4px 0 10px 0;'>", unsafe_allow_html=True)
        else:
            st.warning("扫描完成，当前暂无标的完全触发该策略入场信号。波段交易最关键的是耐心等待确定性机会，严禁盲目追高开仓。")

        # 蓄势观察池
        with st.expander(f"👀 查看蓄势观察池标的 ({len(pending_results)} 只标的接近形成机会)", expanded=False):
            st.caption("提示: 以下标的已满足部分均线或形态条件，但仍需等待放量企稳或价格突破确认：")
            for r in pending_results[:30]:
                st.markdown(f"- **{r['name']}** (`{r['symbol']}` | 确定性 {r['certainty_score']:.1f}分): 已满足 {r['met_count']} 项，尚缺: `{r['pending_details']}`")
