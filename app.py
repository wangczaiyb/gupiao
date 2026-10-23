"""
A 股波段交易辅助系统 · 核心入口 (Streamlit Application)
支持沪深北全市场 (主板、创业板、科创板、北交所) 波段策略、严格回测、风控计算与模拟交易
"""

import os
import sys

# 确保当前项目根目录在 python 搜索路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import streamlit as st

from core.paper_account import PaperAccountManager
from core.risk_manager import RiskBudgetConfig, RiskManager
from data_provider.ai_advisor import AIAdvisor
from data_provider.manager import DataManager
from ui.components import inject_custom_css
from ui.page_backtest import render_backtest_page
from ui.page_overview import render_overview_page
from ui.page_paper_trading import render_paper_trading_page
from ui.page_screener import render_screener_page
from ui.page_settings import render_settings_page
from ui.page_stock_detail import render_stock_detail_page


# 页面全局配置
st.set_page_config(
    page_title="A 股波段交易辅助系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_system_components():
    """初始化并缓存核心单例服务"""
    data_mgr = DataManager(db_path="data/stock_analysis.db", cache_dir="data/cache")
    paper_mgr = PaperAccountManager(db_path="data/stock_analysis.db", initial_capital=100000.0)
    risk_mgr = RiskManager(RiskBudgetConfig(total_capital=100000.0))
    ai_adv = AIAdvisor()
    return data_mgr, paper_mgr, risk_mgr, ai_adv


def main():
    # 注入现代金融样式
    inject_custom_css()

    data_manager, paper_manager, risk_manager, ai_advisor = get_system_components()

    # 侧边栏导航
    with st.sidebar:
        st.markdown("## 📈 A 股波段辅助系统")
        st.caption("沪深北全市场 · 几天到几周波段策略")

        nav_choice = st.radio(
            "功能导航",
            [
                "📊 市场总览与自选",
                "📈 股票详情与分析",
                "🔍 策略选股与扫描",
                "🧪 历史回测与检验",
                "💼 模拟交易与复盘",
                "⚙️ 系统设置与诊断",
            ],
            index=0,
        )

        st.markdown("---")
        st.markdown("### 🛡️ 纪律与风控准则")
        st.markdown("""
        1. **顺势而为**: 不在下跌趋势中左侧盲目抄底
        2. **严格止损**: 绝不把波段交易拖延成长线套牢
        3. **仓位约束**: 单票不超过25%，总仓留有现金垫
        4. **拒绝偷价**: 信号收盘确认，次日开盘按规则执行
        """)

        st.markdown("---")
        st.caption("版本: v1.0.0 | 开源协议: MIT | 资金标示: 模拟演练")

    # 路由渲染页面
    if nav_choice == "📊 市场总览与自选":
        render_overview_page(data_manager)
    elif nav_choice == "📈 股票详情与分析":
        render_stock_detail_page(data_manager, paper_manager, risk_manager, ai_advisor)
    elif nav_choice == "🔍 策略选股与扫描":
        render_screener_page(data_manager)
    elif nav_choice == "🧪 历史回测与检验":
        render_backtest_page(data_manager)
    elif nav_choice == "💼 模拟交易与复盘":
        render_paper_trading_page(data_manager, paper_manager)
    elif nav_choice == "⚙️ 系统设置与诊断":
        render_settings_page(data_manager, risk_manager, ai_advisor)


if __name__ == "__main__":
    main()
