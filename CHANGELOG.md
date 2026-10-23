# 📝 更新日志 (CHANGELOG)

所有版本演进严格遵循语义化版本规范，所有功能变动均经自动化测试套件验证。

---

## [v2.0.0] - 2026-10-23 (A 股量化系统高标准增量升级)

### 🚀 新增功能 (Added)
- **AlphaSift 风格多因子库与确定性评分 (`core/factors.py`)**:
  - 新增趋势强度 (Trend)、动量 (Momentum)、相对强度 (RS vs 基准)、成交量爆发 (Volume Surge)、波动率收缩 (Volatility Contraction) 与流动性 (Liquidity) 6 大标准化量化因子。
  - 实现 0~100 分多因子加权确定性评分 (Certainty Score)，支持跨标的排序与优先级竞争。
  - 缺失关键数据时直接返回 `None`，严禁缺失值自动补成有利信号。
- **两套全新经典波段策略 (`core/strategies/`)**:
  - `rs_momentum.py`: 相对强度动量策略，专注于市场领涨龙头股的顺势动量。
  - `volatility_contraction.py`: 波动收缩突破策略 (VCP)，捕捉窄幅蓄势后的放量起爆拐点。
- **可恢复批处理扫描调度器 (`data_provider/batch_scanner.py`)**:
  - 实现基于 SQLite 的断点续扫、批次单步推进、指数退避重试与失败日志记录 (`data/batch_scan_errors.log`)。
  - 包含请求频率限流保护，避免高频请求冲击数据接口。
- **全市场动态证券目录与多维度标的池 (`data_provider/manager.py`)**:
  - 动态从公开数据源获取全市场 5000+ 标的目录并持久化于本地 SQLite (`stock_basic_info`)。
  - 支持自选股、沪深300指数核心池、中证500、中证1000与全市场范围选择。
- **持仓体检与风控诊断模块 (`core/portfolio_health.py` & `ui/page_portfolio_health.py`)**:
  - 支持手动录入或 CSV 批量导入持仓明细（代码、成本价、股数、买入日期）。
  - 输出均线多空结构、近期支撑阻力位、建议移动止损点、浮亏超标报警与行业/单票集中度透视。
  - 联动 AI Agent 生成客观风控复盘备忘。
- **AKQuant 独立回测验证适配器 (`core/akquant_adapter.py`)**:
  - 提供对 `akquant` 事件驱动回测的独立交叉验证能力，未安装时提供平滑状态降级。
- **真实小资金风控强化 (`core/risk_manager.py`)**:
  - 默认本金调整为贴近散户实盘的 5000 元（支持自定义），支持最低佣金 0/1/5 元可配置。
  - 增加科创板/创业板/北交所板块交易权限前置校验。
  - 细化整手申报资金不足、超单票上限与小资金规费过高预警诊断。

### 🔧 核心缺陷修复 (Fixed)
- **修复未知股票代码静默按沪市主板规则处理的问题 (`core/rules.py`)**:
  - 未知代码在 `get_board_rules` 中明确抛出 `ValueError`，在 `round_trade_quantity` 中安全截断为 0 股，杜绝非法代码静默按主板成交。
- **修复 EMA20 回踩缺少负向边界约束导致暴跌股被误判为回踩成功的问题 (`core/strategies/trend_pullback.py`)**:
  - 增加了 `-pullback_margin <= dist_to_ema20 <= pullback_margin` 双向约束，严重跌破均线时明确标记为待满足破位。
- **修复 ST 股票与上市无涨跌幅规则未透传至回测引擎的问题 (`core/backtest_engine.py`)**:
  - 在计算开盘与盘中涨跌停时，完整透传并适配历史 ST 状态与无涨跌幅窗口。
- **修复回测买入信号同日多标的竞争时缺少排序机制的问题 (`core/backtest_engine.py`)**:
  - 引入跨标的确定性优先得分与盈亏比降序竞争机制，杜绝遍历随机先后偏差。
- **修复 Parquet 读写异常被无提示静默忽略的问题 (`data_provider/manager.py` & `requirements.txt`)**:
  - 在 `requirements.txt` 中显式锁定 `pyarrow>=12.0.0`，在写缓存时记录完整日志与错误提示。
- **修复全市场扫描实际仅包含 48 只硬编码代表股的问题 (`ui/page_screener.py`)**:
  - 重构选股扫描器，对接真实动态证券目录与多策略分层发现。

### 🧪 自动化测试套件 (Tests)
- 单元测试由 27 项扩充至 **37 项**，新增 `tests/test_v2_features.py`，覆盖因子、新策略、小资金风控、持仓体检与断点续扫。
- 执行 `pytest tests/ -v` 全部 37 项测试 100% 通过。
