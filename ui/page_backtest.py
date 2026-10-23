"""
页面 4: 策略回测与验证分析 (Backtest & Performance Analytics)
满足首版重点要求：
1. 真实 T+1 与下一交易日开盘 (Next-Bar) 撮合执行
2. 同日触及止损止盈采用保守假设 (先触及止损)
3. 跳空跌破止损以实际开盘价撮合
4. 佣金 (含5元最低限制)、印花税、过户费与滑点真实扣除
5. 多股票组合共享账户资金池
6. 样本内/样本外区间对比与基准指数 (沪深300) 收益对比
"""

from datetime import date, datetime
import streamlit as st
import pandas as pd

from core.backtest_engine import BacktestEngine
from core.strategies.range_breakout import RangeBreakoutStrategy
from core.strategies.trend_pullback import TrendPullbackStrategy
from data_provider.manager import DataManager
from ui.charts import create_equity_curve_chart


def render_backtest_page(data_manager: DataManager):
    st.markdown("## 🧪 策略回测与稳健性检验")
    st.caption("提示: 本回测引擎严格遵循 A 股交易制度（T+1、板块申报单位、跌停无法卖出、涨停无法买入、跳空滑点与最保守同日止损假设），杜绝未来数据偷价。")

    # 1. 回测配置侧边栏/折叠卡片
    with st.expander("⚙️ 回测参数与执行假设配置", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            strat_name = st.selectbox("回测策略选择", ["趋势回调观察策略", "区间突破观察策略"])
            universe_mode = st.selectbox("测试标的池", ["自选股全组合 (多标的共享资金)", "单一标的深度回测"])
            if universe_mode == "单一标的深度回测":
                single_symbol = st.text_input("输入测试股票代码", value="600519")
            else:
                single_symbol = ""

        with c2:
            start_dt = st.date_input("回测开始日期", value=date(2023, 1, 1))
            end_dt = st.date_input("回测结束日期", value=date.today())
            split_ratio = st.slider("样本内/样本外验证切分 (Train/Test Split)", min_value=0.5, max_value=0.9, value=0.7, step=0.05, help="前 N% 数据用于规则观察，后 (1-N)% 用于盲测验证")

        with c3:
            init_cap = st.number_input("初始模拟本金 (元)", value=100000.0, step=10000.0)
            comm_rate = st.number_input("佣金费率", value=0.00025, format="%.5f", help="万 2.5")
            slippage = st.number_input("滑点估算比例", value=0.0005, format="%.4f", help="0.05% 滑点")

    # 2. 策略具体参数调优 (非必须，可按需修改)
    with st.expander("🛠️ 策略底层量化参数微调 (默认参数为经典学术与实盘基准)"):
        p_col1, p_col2 = st.columns(2)
        if strat_name == "趋势回调观察策略":
            with p_col1:
                p_fast = st.slider("短期均线周期 EMA", 10, 30, 20)
                p_mid = st.slider("中期趋势均线 EMA", 30, 80, 50)
                p_slow = st.slider("长期基准均线 EMA", 90, 180, 120)
            with p_col2:
                p_rsi_min = st.slider("RSI 吸纳下限", 30.0, 45.0, 38.0)
                p_rsi_max = st.slider("RSI 吸纳上限", 50.0, 65.0, 58.0)
                p_vol_mult = st.slider("企稳放量系数", 0.9, 1.5, 1.05)
            strategy = TrendPullbackStrategy({
                "ema_fast": p_fast, "ema_mid": p_mid, "ema_slow": p_slow,
                "rsi_min": p_rsi_min, "rsi_max": p_rsi_max, "vol_factor": p_vol_mult,
            })
        else:
            with p_col1:
                p_chan = st.slider("唐奇安箱体周期", 15, 60, 20)
                p_squeeze = st.slider("突破前布林带宽上限", 0.15, 0.35, 0.22)
            with p_col2:
                p_vol_break = st.slider("突破放量倍数", 1.2, 2.5, 1.75)
                p_max_rsi = st.slider("RSI 超买过滤上限", 75.0, 90.0, 82.0)
            strategy = RangeBreakoutStrategy({
                "channel_period": p_chan, "squeeze_bandwidth": p_squeeze,
                "vol_breakout_mult": p_vol_break, "max_rsi": p_max_rsi,
            })

    # 3. 运行回测按钮
    if st.button("🚀 启动高保真回测模拟", type="primary", use_container_width=True):
        engine = BacktestEngine(
            initial_capital=init_cap,
            commission_rate=comm_rate,
            min_commission=5.0,
            slippage_rate=slippage,
        )

        stock_dfs = {}
        with st.spinner("正在加载回测历史数据并执行因果撮合计算..."):
            if universe_mode == "单一标的深度回测":
                clean_s = single_symbol.strip()
                df, _ = data_manager.get_daily_bars(clean_s, start_date=str(start_dt), end_date=str(end_dt))
                if len(df) > 0:
                    stock_dfs[clean_s] = df
            else:
                watchlist = data_manager.get_watchlist()
                for item in watchlist:
                    sym = item["symbol"]
                    df, _ = data_manager.get_daily_bars(sym, start_date=str(start_dt), end_date=str(end_dt))
                    if len(df) > 0:
                        stock_dfs[sym] = df

            # 加载沪深300作为比较基准
            bench_df = data_manager.get_benchmark_bars("000300", start_date=str(start_dt))

        if not stock_dfs:
            st.error("未能获取到测试标的在所选日期区间的有效日线数据，请检查日期或代码。")
            return

        # 执行回测
        metrics, equity_df, closed_trades = engine.run_portfolio(
            stock_dfs=stock_dfs,
            strategy=strategy,
            benchmark_df=bench_df,
            train_test_split_ratio=split_ratio,
        )

        # 4. 渲染核心回测指标看板
        st.markdown("### 📊 回测表现总览")
        m_c1, m_c2, m_c3, m_c4, m_c5, m_c6 = st.columns(6)

        ret_delta_color = "normal" if metrics.total_return_pct >= 0 else "inverse"
        m_c1.metric("累计净收益率", f"{metrics.total_return_pct*100:.2f}%", f"年化 {metrics.annualized_return_pct*100:.2f}%", delta_color=ret_delta_color)
        m_c2.metric("最大回撤 (MDD)", f"{metrics.max_drawdown_pct*100:.2f}%", delta_color="inverse")
        m_c3.metric("夏普比率 (Sharpe)", f"{metrics.sharpe_ratio:.2f}", help="无风险利率假定 2.5%")
        m_c4.metric("交易胜率", f"{metrics.win_rate_pct*100:.1f}%", f"{metrics.winning_trades}胜 / {metrics.losing_trades}负")
        m_c5.metric("单笔盈亏比", f"{metrics.profit_loss_ratio:.2f} : 1", f"均盈+{metrics.avg_win_pct*100:.1f}% / 均亏-{metrics.avg_loss_pct*100:.1f}%")
        m_c6.metric("总交易次数", f"{metrics.total_trades} 笔", f"平均持股 {metrics.avg_holding_days:.1f} 天")

        # 5. 样本外验证与基准超额对比
        st.markdown("#### 🎯 样本外验证与基准超额对比")
        sub_c1, sub_c2, sub_c3, sub_c4 = st.columns(4)
        sub_c1.metric("基准指数 (沪深300) 收益", f"{metrics.benchmark_return_pct*100:.2f}%" if metrics.benchmark_return_pct is not None else "暂无")
        sub_c2.metric("超越基准 Alpha", f"{metrics.alpha_pct*100:.2f}%" if metrics.alpha_pct is not None else "暂无", delta_color="normal")
        sub_c3.metric("样本内 (Train) 收益", f"{metrics.in_sample_return_pct*100:.2f}%" if metrics.in_sample_return_pct is not None else "暂无")
        sub_c4.metric("样本外 (Test) 收益", f"{metrics.out_of_sample_return_pct*100:.2f}%" if metrics.out_of_sample_return_pct is not None else "暂无")

        st.caption(f"🛡️ 回测期间累计扣除实际规费与交易费用: **¥{metrics.total_fees_paid:.2f} 元** (印花税减半 0.05%、过户费 0.001%、最低佣金 5 元及真实滑点)")

        # 6. 净值走势曲线与回撤图
        st.markdown("#### 📈 组合累计净值曲线 vs 基准走势")
        fig_equity = create_equity_curve_chart(equity_df, bench_df, initial_capital=init_cap)
        st.plotly_chart(fig_equity, use_container_width=True)

        # 7. 详细交易记录表与复盘审计
        st.markdown("#### 📑 逐笔已平仓交易明细清单")
        if closed_trades:
            trade_rows = []
            for t in closed_trades:
                trade_rows.append({
                    "交易编号": t.trade_id,
                    "代码": t.symbol,
                    "买入日期": t.entry_date,
                    "买入均价": t.entry_price,
                    "卖出日期": t.exit_date,
                    "卖出均价": t.exit_price,
                    "持仓股数": t.shares,
                    "净盈亏(元)": t.net_pnl,
                    "收益率": f"{(t.pnl_pct or 0.0)*100:.2f}%",
                    "持仓天数": t.holding_days,
                    "退出原因": t.exit_reason,
                    "跳空出场": "是" if t.is_gap_exit else "否",
                    "同日冲突保守判定": "是" if t.is_conservative_conflict else "否",
                })
            df_trades = pd.DataFrame(trade_rows)
            st.dataframe(df_trades, use_container_width=True)

            # CSV 导出功能
            csv_data = df_trades.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 导出回测交易流水为 CSV 文件",
                data=csv_data,
                file_name=f"backtest_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )
        else:
            st.info("所选区间或标的池内未触发完成闭环的交易。")
