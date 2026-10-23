"""
页面 6: 系统设置与数据源诊断 (Settings & Diagnostics Page)
包含：
1. 数据源覆盖范围与可用性实时报告 (沪深北全市场支持状态)
2. 本地缓存管理与磁盘占用清理
3. 组合风控核心参数全局配置
4. 可选 AI 大模型接入配置
"""

import os
import streamlit as st

from core.risk_manager import RiskBudgetConfig, RiskManager
from data_provider.ai_advisor import AIAdvisor
from data_provider.manager import DataManager


def render_settings_page(
    data_manager: DataManager,
    risk_manager: RiskManager,
    ai_advisor: AIAdvisor,
):
    st.markdown("## ⚙️ 系统设置与数据源诊断")

    # 1. 数据源诊断与全市场覆盖报告
    st.markdown("### 📡 数据源覆盖与连通性诊断")
    report = data_manager.get_coverage_report()

    st.markdown(f"""
    - **计费模式**: `{report['fee_mode']}`
    - **本地缓存目录**: `{report['cache_directory']}`
    - **本地数据库路径**: `{report['db_path']}`
    - **网络代理防护**: `{report['proxy_protection']}`
    """)

    # 展现五大板块支持情况
    board_status_data = []
    for b_name, b_info in report["supported_boards"].items():
        board_status_data.append({
            "交易所及板块": b_name,
            "代码特征": b_info["code_prefix"],
            "接入数据源方案": b_info["source"],
            "验证状态": b_info["status"],
        })
    st.dataframe(board_status_data, use_container_width=True)

    # 2. 缓存管理
    st.markdown("---")
    st.markdown("### 💾 本地历史日线缓存管理")
    cache_dir = data_manager.cache_dir
    cache_files = os.listdir(cache_dir) if os.path.exists(cache_dir) else []
    total_size = sum(os.path.getsize(os.path.join(cache_dir, f)) for f in cache_files if os.path.isfile(os.path.join(cache_dir, f)))

    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"当前缓存文件数: **{len(cache_files)} 个标的** | 占用磁盘空间: **{total_size / (1024*1024):.2f} MB**")
        st.caption("缓存机制：首次查询标的时自动落盘，日间刷新直接读取磁盘秒级响应，避免每次刷新全量爬取上游接口。")
    with c2:
        if st.button("🧹 一键清空所有缓存", use_container_width=True):
            for f in cache_files:
                try:
                    os.remove(os.path.join(cache_dir, f))
                except Exception:
                    pass
            st.success("本地磁盘缓存已全部清理！")
            st.rerun()

    # 3. 组合风控全局参数配置
    st.markdown("---")
    st.markdown("### 🛡️ 组合风控全局预算配置")
    cfg = risk_manager.config
    with st.form("risk_config_form"):
        rc1, rc2 = st.columns(2)
        with rc1:
            cfg_capital = st.number_input("模拟账户总资金预算 (元)", value=float(cfg.total_capital), step=10000.0)
            cfg_risk_pct = st.slider("单笔交易最大允许本金亏损比例 (%)", min_value=0.5, max_value=3.0, value=float(cfg.risk_per_trade_pct * 100), step=0.1)
            cfg_single_pct = st.slider("单只股票最大持仓资金占比上限 (%)", min_value=10, max_value=50, value=int(cfg.max_single_stock_pct * 100), step=5)
        with rc2:
            cfg_max_pos = st.number_input("最大允许同时持仓标的只数", min_value=1, max_value=15, value=int(cfg.max_concurrent_positions), step=1)
            cfg_ind_pct = st.slider("单一行业最大敞口上限 (%)", min_value=20, max_value=60, value=int(cfg.max_industry_exposure_pct * 100), step=5)
            cfg_mdd_stop = st.slider("组合累计回撤熔断警戒线 (%)", min_value=5, max_value=25, value=int(cfg.max_drawdown_stop_trading_pct * 100), step=1)

        save_risk = st.form_submit_button("💾 保存风控参数配置", type="primary", use_container_width=True)
        if save_risk:
            risk_manager.config = RiskBudgetConfig(
                total_capital=cfg_capital,
                risk_per_trade_pct=cfg_risk_pct / 100.0,
                max_single_stock_pct=cfg_single_pct / 100.0,
                max_concurrent_positions=int(cfg_max_pos),
                max_industry_exposure_pct=cfg_ind_pct / 100.0,
                max_drawdown_stop_trading_pct=cfg_mdd_stop / 100.0,
            )
            st.success("全局风控参数已成功更新！")

    # 4. 可选 AI 大模型配置
    st.markdown("---")
    st.markdown("### 🤖 可选 AI 智能解构配置")
    st.caption("提示: 本模块纯属可选增强，若不填写 API Key，系统默认使用高性能离线规则量化引擎，不会影响任何筛选、交易、回测与风控功能。")

    with st.form("ai_config_form"):
        ai_c1, ai_c2 = st.columns(2)
        with ai_c1:
            ai_key = st.text_input("OpenAI / 兼容接口 API Key", value=ai_advisor.api_key, type="password", placeholder="sk-...")
            ai_url = st.text_input("接口 Base URL", value=ai_advisor.base_url, placeholder="https://api.openai.com/v1")
        with ai_c2:
            ai_model = st.text_input("模型名称 (Model)", value=ai_advisor.model, placeholder="gpt-4o-mini 或 deepseek-chat 或 qwen-plus")

        save_ai = st.form_submit_button("💾 保存 AI 配置", use_container_width=True)
        if save_ai:
            ai_advisor.api_key = ai_key.strip()
            ai_advisor.base_url = ai_url.strip()
            ai_advisor.model = ai_model.strip()
            ai_advisor.is_configured = bool(ai_advisor.api_key and len(ai_advisor.api_key) > 5)
            st.success("AI 配置已保存！")
