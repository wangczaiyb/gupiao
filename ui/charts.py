"""
Plotly 交互式金融图表模块
专为 A 股红涨绿跌经典配色定制 (上涨红 #eb445a / #f53f3f, 下跌绿 #00b42a / #2ba471)
支持：
1. 主图：K 线 + 均线系统 (EMA20, EMA50, EMA120) + 唐奇安/布林通道 + 候选入场/止损参考线
2. 副图 1：成交量柱状图 (随涨跌变色) + 5日/20日均量线
3. 副图 2：RSI 动量指标曲线 + 30/70 超买超卖警示区间
4. 回测净值图：策略净值曲线 vs 基准指数 (沪深300) 收益走势对比 + 回撤阴影图
"""

from typing import List, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_candlestick_chart(
    df: pd.DataFrame,
    symbol: str,
    name: str = "",
    stop_loss_price: Optional[float] = None,
    entry_price: Optional[float] = None,
    take_profit_price: Optional[float] = None,
    height: int = 700,
) -> go.Figure:
    """
    创建专业三合一股票波段技术分析图
    """
    if len(df) == 0:
        fig = go.Figure()
        fig.update_layout(title="暂无 K 线数据", template="plotly_white")
        return fig

    # 仅展示最近 120 根 K 线，保证图表清晰与流畅
    plot_df = df.iloc[-120:].copy() if len(df) > 120 else df.copy()

    # 创建带有主副图的子图框架
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.60, 0.22, 0.18],
        subplot_titles=(
            f"{name} ({symbol}) 日 K 线与波段均线支撑",
            "成交量 (股) 与 5/20 日均量",
            "RSI 强弱指标 (14)",
        ),
    )

    # A 股色彩：阳线红，阴线绿
    colors = np.where(plot_df["close"] >= plot_df["open"], "#f53f3f", "#00b42a")

    # 1. 主图：蜡烛图
    fig.add_trace(
        go.Candlestick(
            x=plot_df["date"],
            open=plot_df["open"],
            high=plot_df["high"],
            low=plot_df["low"],
            close=plot_df["close"],
            name="K线",
            increasing_line_color="#f53f3f",
            increasing_fillcolor="#f53f3f",
            decreasing_line_color="#00b42a",
            decreasing_fillcolor="#00b42a",
        ),
        row=1,
        col=1,
    )

    # 叠加均线
    if "ema_20" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df["date"], y=plot_df["ema_20"], mode="lines", name="EMA(20) 短期支撑", line=dict(color="#fa8c16", width=1.5)),
            row=1,
            col=1,
        )
    if "ema_50" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df["date"], y=plot_df["ema_50"], mode="lines", name="EMA(50) 中期趋势", line=dict(color="#1890ff", width=1.8)),
            row=1,
            col=1,
        )
    if "ema_120" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df["date"], y=plot_df["ema_120"], mode="lines", name="EMA(120) 多空基准", line=dict(color="#722ed1", width=2.0)),
            row=1,
            col=1,
        )

    # 叠加候选入场、止损与止盈水平线
    if entry_price and entry_price > 0:
        fig.add_hline(
            y=entry_price,
            line_dash="dash",
            line_color="#1890ff",
            line_width=1.5,
            annotation_text=f"入场参考: {entry_price:.2f}",
            annotation_position="top right",
            row=1,
            col=1,
        )
    if stop_loss_price and stop_loss_price > 0:
        fig.add_hline(
            y=stop_loss_price,
            line_dash="dash",
            line_color="#f53f3f",
            line_width=2.0,
            annotation_text=f"止损警戒: {stop_loss_price:.2f}",
            annotation_position="bottom right",
            row=1,
            col=1,
        )
    if take_profit_price and take_profit_price > 0:
        fig.add_hline(
            y=take_profit_price,
            line_dash="dash",
            line_color="#52c41a",
            line_width=1.5,
            annotation_text=f"止盈目标: {take_profit_price:.2f}",
            annotation_position="top right",
            row=1,
            col=1,
        )

    # 2. 副图 1: 成交量
    fig.add_trace(
        go.Bar(
            x=plot_df["date"],
            y=plot_df["volume"],
            name="成交量(股)",
            marker_color=colors,
            opacity=0.85,
        ),
        row=2,
        col=1,
    )
    if "vol_ma5" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df["date"], y=plot_df["vol_ma5"], mode="lines", name="MA5 均量", line=dict(color="#fa8c16", width=1.2)),
            row=2,
            col=1,
        )
    if "vol_ma20" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df["date"], y=plot_df["vol_ma20"], mode="lines", name="MA20 均量", line=dict(color="#1890ff", width=1.2)),
            row=2,
            col=1,
        )

    # 3. 副图 2: RSI 动量
    if "rsi_14" in plot_df.columns:
        fig.add_trace(
            go.Scatter(x=plot_df["date"], y=plot_df["rsi_14"], mode="lines", name="RSI(14)", line=dict(color="#13c2c2", width=1.5)),
            row=3,
            col=1,
        )
        # 超买超卖参考线 (70/30)
        fig.add_hline(y=70, line_dash="dot", line_color="#ff4d4f", line_width=1.0, row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#52c41a", line_width=1.0, row=3, col=1)

    # 布局美化
    fig.update_layout(
        height=height,
        template="plotly_white",
        xaxis_rangeslider_visible=False,
        margin=dict(l=40, r=40, t=40, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig


def create_equity_curve_chart(
    equity_df: pd.DataFrame,
    benchmark_df: Optional[pd.DataFrame] = None,
    initial_capital: float = 100000.0,
    height: int = 480,
) -> go.Figure:
    """
    绘制回测资产净值曲线与基准对比
    """
    if len(equity_df) == 0:
        fig = go.Figure()
        fig.update_layout(title="暂无净值数据", template="plotly_white")
        return fig

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.72, 0.28],
        subplot_titles=("组合累计净值曲线 (扣除全部佣金/印花税/过户费/滑点)", "组合动态回撤 (%)"),
    )

    # 策略净值
    strat_net_values = equity_df["total_equity"] / initial_capital
    fig.add_trace(
        go.Scatter(
            x=equity_df["date"],
            y=strat_net_values,
            mode="lines",
            name="波段策略净值",
            line=dict(color="#1890ff", width=2.5),
        ),
        row=1,
        col=1,
    )

    # 基准净值 (例如沪深300)
    if benchmark_df is not None and len(benchmark_df) > 0 and "close" in benchmark_df.columns:
        b_aligned = benchmark_df[benchmark_df["date"].isin(equity_df["date"])].copy()
        if len(b_aligned) > 0:
            b_start_p = b_aligned["close"].iloc[0]
            if b_start_p > 0:
                b_net_vals = b_aligned["close"] / b_start_p
                fig.add_trace(
                    go.Scatter(
                        x=b_aligned["date"],
                        y=b_net_vals,
                        mode="lines",
                        name="基准指数 (沪深300)",
                        line=dict(color="#8c8c8c", width=1.5, dash="dash"),
                    ),
                    row=1,
                    col=1,
                )

    # 计算动态回撤
    cummax = equity_df["total_equity"].cummax()
    drawdown = (equity_df["total_equity"] - cummax) / cummax * 100.0

    fig.add_trace(
        go.Scatter(
            x=equity_df["date"],
            y=drawdown,
            mode="lines",
            name="回撤幅度 (%)",
            fill="tozeroy",
            line=dict(color="#f53f3f", width=1.0),
            fillcolor="rgba(245, 63, 63, 0.15)",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        height=height,
        template="plotly_white",
        margin=dict(l=40, r=40, t=30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig
