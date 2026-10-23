"""
页面 3: 股票筛选与市场机会扫描 (Screener Page)
特性：
1. 可配置股票池：按板块 (主板/创业板/科创板/北交所)、流动性、上市时长与风险状态过滤
2. 过滤 ST、*ST、退市整理与停牌标的
3. 全市场扫描进度展示、本地缓存加速与失败自动重试
4. 筛选结果清单：展示触发策略、入场参考价、止损位、盈亏比与一键加入自选
"""

import time
import streamlit as st
import pandas as pd

from core.stock_info import filter_stock_pool, parse_stock_profile
from core.strategies.range_breakout import RangeBreakoutStrategy
from core.strategies.trend_pullback import TrendPullbackStrategy
from data_provider.manager import DataManager
from ui.components import render_board_badge


def render_screener_page(data_manager: DataManager):
    st.markdown("## 🔍 波段策略选股与机会扫描")

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
            strat_type = st.selectbox("选择扫描策略", ["趋势回调观察策略", "区间突破观察策略"])
        with col_m2:
            scan_scope = st.selectbox("扫描股票池范围", ["自选股清单 (极速)", "核心代表性指数成分池 (~50只/快速)", "沪深北全市场样本池 (~150只/深度)"])

    # 准备目标股票池
    boards_selected = []
    if inc_sh: boards_selected.append("SH_MAIN")
    if inc_sz: boards_selected.append("SZ_MAIN")
    if inc_chinext: boards_selected.append("CHINEXT")
    if inc_star: boards_selected.append("STAR")
    if inc_bse: boards_selected.append("BSE")

    # 触发扫描按钮
    if st.button("🚀 开始扫描波段机会", type="primary", use_container_width=True):
        candidate_profiles = []

        if scan_scope == "自选股清单 (极速)":
            raw_stocks = data_manager.get_watchlist()
            for s in raw_stocks:
                prof = parse_stock_profile(s["symbol"], s["name"])
                candidate_profiles.append(prof)
        else:
            # 内置高质量全市场代表性池
            core_universe = [
                # 沪市主板
                ("600519", "贵州茅台"), ("601318", "中国平安"), ("600036", "招商银行"), ("601899", "紫金矿业"),
                ("601138", "工业富联"), ("600900", "长江电力"), ("601088", "中国神华"), ("600030", "中信证券"),
                ("601668", "中国建筑"), ("603288", "海天味业"), ("600436", "片仔癀"), ("601988", "中国银行"),
                # 深市主板
                ("000001", "平安银行"), ("002594", "比亚迪"), ("000333", "美的集团"), ("002475", "立讯精密"),
                ("000858", "五粮液"), ("000002", "万科A"), ("002415", "海康威视"), ("000725", "京东方A"),
                ("000651", "格力电器"), ("002371", "北方华创"), ("002241", "歌尔股份"), ("002142", "宁波银行"),
                # 创业板
                ("300750", "宁德时代"), ("300059", "东方财富"), ("300124", "汇川技术"), ("300760", "迈瑞医疗"),
                ("300274", "阳光电源"), ("300014", "亿纬锂能"), ("300433", "蓝思科技"), ("300454", "深信服"),
                # 科创板
                ("688981", "中芯国际"), ("688012", "中微公司"), ("688111", "金山办公"), ("688041", "海光信息"),
                ("688256", "寒武纪"), ("688223", "晶科能源"), ("688008", "澜起科技"), ("688692", "达梦数据"),
                # 北交所
                ("920211", "倍益康"), ("920002", "万达轴承"), ("835185", "贝特瑞"), ("832023", "田野股份"),
                ("871642", "通易航天"), ("834599", "同力股份"), ("831010", "凯德石英"), ("833533", "骏创科技"),
            ]
            for sym, name in core_universe:
                prof = parse_stock_profile(sym, name)
                candidate_profiles.append(prof)

        # 过滤标的池
        valid_profiles = filter_stock_pool(
            stocks=candidate_profiles,
            allowed_boards=boards_selected,
            exclude_st=exclude_st,
            exclude_delisting=exclude_delist,
            exclude_suspended=exclude_susp,
            min_listing_days=min_days,
        )

        st.info(f"经过板块与风险前置过滤后，共有 **{len(valid_profiles)}** 只标的进入策略扫描执行序列...")

        # 选定策略
        if strat_type == "趋势回调观察策略":
            strategy = TrendPullbackStrategy()
        else:
            strategy = RangeBreakoutStrategy()

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
                results.append({
                    "symbol": p.symbol,
                    "name": p.name,
                    "board_key": p.board_key,
                    "board_name": p.board_name,
                    "latest_price": latest_p,
                    "signal_type": sig.signal_type.value,
                    "is_actionable": sig.is_actionable,
                    "entry_price": sig.candidate_entry_price,
                    "stop_loss": sig.stop_loss_price,
                    "take_profit": sig.take_profit_price,
                    "stop_rationale": sig.stop_loss_rationale,
                    "met_count": len(sig.conditions_met),
                    "pending_count": len(sig.conditions_pending),
                    "met_details": "; ".join(sig.conditions_met[:2]),
                    "pending_details": "; ".join(sig.conditions_pending[:2]),
                })

        progress_bar.empty()
        status_text.empty()

        # 展示筛选结果
        actionable_results = [r for r in results if r["is_actionable"]]
        pending_results = [r for r in results if not r["is_actionable"]]

        st.markdown(f"### 🎯 扫描结果汇总: 发现 **{len(actionable_results)}** 只候选买点标的")

        if actionable_results:
            st.success("以下标的已完全满足当前波段策略入场条件：")
            for r in actionable_results:
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([1.5, 1.2, 1.2, 2.5, 1.2])
                    c1.markdown(f"**{r['name']}** (`{r['symbol']}`)")
                    c2.markdown(render_board_badge(r["board_key"], r["board_name"]), unsafe_allow_html=True)
                    c3.markdown(f"现价: **¥{r['latest_price']:.2f}**")
                    c4.markdown(f"入场参考: ¥{r['entry_price']:.2f} | 止损: **¥{r['stop_loss']:.2f}** | 止盈: **¥{r['take_profit']:.2f}**")
                    if c5.button("➕ 加入自选", key=f"add_scan_{r['symbol']}"):
                        data_manager.add_to_watchlist(r["symbol"], r["name"], f"【{strat_type}】扫描命中")
                        st.success(f"已加入自选: {r['name']}")
                st.markdown("<hr style='margin: 4px 0 10px 0;'>", unsafe_allow_html=True)
        else:
            st.warning("全市场扫描完成，当前暂无标的完全触发该策略入场信号。波段交易最关键的是耐心等待确定性机会，切勿勉强交易。")

        # 蓄势观察池
        with st.expander(f"👀 查看蓄势观察池标的 ({len(pending_results)} 只标的接近形成机会)", expanded=False):
            st.caption("提示: 以下标的已满足部分均线或形态条件，但仍需等待放量企稳或价格突破确认：")
            for r in pending_results[:30]:
                st.markdown(f"- **{r['name']}** (`{r['symbol']}`): 已满足 {r['met_count']} 项，尚缺: `{r['pending_details']}`")
