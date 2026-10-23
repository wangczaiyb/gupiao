"""
UI 组件与现代金融控制台样式
提供自适应宽屏/移动端的卡片、状态徽章、风险提示与条件拆解面板
"""

import streamlit as st


def inject_custom_css():
    """注入现代金融终端的高质感 CSS 样式"""
    st.markdown("""
    <style>
    /* 全局页面字体与内边距调优 */
    .main .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2.5rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    
    /* 核心指标卡片 */
    .metric-card {
        background: #ffffff;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        border: 1px solid #ebeef5;
        margin-bottom: 12px;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    }
    .metric-title {
        font-size: 0.85rem;
        color: #606266;
        font-weight: 500;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #1f2d3d;
        letter-spacing: -0.5px;
    }
    .metric-sub {
        font-size: 0.78rem;
        color: #909399;
        margin-top: 4px;
    }

    /* 红色上涨与绿色下跌 */
    .val-up {
        color: #f53f3f !important;
    }
    .val-down {
        color: #00b42a !important;
    }

    /* 状态徽章 */
    .tag-badge {
        display: inline-block;
        padding: 2px 8px;
        font-size: 0.75rem;
        border-radius: 4px;
        font-weight: 500;
        margin-right: 6px;
    }
    .tag-sh-main { background: #e8f4ff; color: #1677ff; border: 1px solid #91caff; }
    .tag-sz-main { background: #f6ffed; color: #389e0d; border: 1px solid #b7eb8f; }
    .tag-chinext { background: #fff7e6; color: #d46b08; border: 1px solid #ffd591; }
    .tag-star { background: #f9f0ff; color: #722ed1; border: 1px solid #d3adf7; }
    .tag-bse { background: #fff0f6; color: #c41d7f; border: 1px solid #ffadd2; }
    .tag-st { background: #fff1f0; color: #cf1322; border: 1px solid #ffa39e; }

    /* 条件清单盒子 */
    .condition-box-met {
        background: #f6ffed;
        border-left: 4px solid #52c41a;
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        margin-bottom: 8px;
        font-size: 0.88rem;
        color: #262626;
    }
    .condition-box-pending {
        background: #fffbe6;
        border-left: 4px solid #faad14;
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        margin-bottom: 8px;
        font-size: 0.88rem;
        color: #262626;
    }
    .condition-box-risk {
        background: #fff2e8;
        border-left: 4px solid #ff4d4f;
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        margin-bottom: 8px;
        font-size: 0.88rem;
        color: #262626;
    }

    /* 免责与模拟标示 */
    .sim-banner {
        background: #e6f7ff;
        border: 1px solid #91d5ff;
        border-radius: 6px;
        padding: 10px 16px;
        color: #0958d9;
        font-size: 0.86rem;
        margin-bottom: 16px;
    }
    </style>
    """, unsafe_allow_html=True)


def render_board_badge(board_key: str, board_name: str) -> str:
    """生成板块彩色徽章 HTML"""
    css_class = "tag-sh-main"
    if board_key == "SZ_MAIN":
        css_class = "tag-sz-main"
    elif board_key == "CHINEXT":
        css_class = "tag-chinext"
    elif board_key == "STAR":
        css_class = "tag-star"
    elif board_key == "BSE":
        css_class = "tag-bse"
    return f'<span class="tag-badge {css_class}">{board_name}</span>'
