# 开源项目采用与第三方声明 (Third-Party Notices)

本项目在设计与量化架构演进过程中，参考并借鉴了以下优秀开源项目的思想与成熟实现：

### 1. ZhuLinsen/alphasift
- **来源代码库**: https://github.com/ZhuLinsen/alphasift
- **许可证**: MIT License
- **借鉴与吸收**:
  - 参考其“分层发现 (Layered Discovery)”与“确定性评分 (Certainty Score)”设计理念；
  - 吸收其可配置多策略扫描与量化候选跟踪机制；
  - 本项目在此基础上针对 A 股交易制度（主板/创业板/科创板/北交所申报递增单位与严格涨跌幅）进行了全自研原生实现。

### 2. akfamily/akquant
- **来源代码库**: https://github.com/akfamily/akquant
- **许可证**: Apache 2.0 / MIT License
- **借鉴与吸收**:
  - 参考其面向国内金融市场的事件驱动回测抽象与撮合验算思路；
  - 在项目中实现了 `AKQuantAdapter` 独立验证适配器，支持双引擎交叉验算。

### 3. microsoft/qlib
- **来源代码库**: https://github.com/microsoft/qlib
- **许可证**: MIT License
- **借鉴与吸收**:
  - 参考其严格因果时间序列指标定义、因子特征标准化与防未来函数泄露方法；
  - 吸收其滚动窗口验证 (Walk-Forward Validation) 与样本内/样本外严格隔离思想。

### 4. ZhuLinsen/daily_stock_analysis
- **来源代码库**: https://github.com/ZhuLinsen/daily_stock_analysis
- **许可证**: MIT License
- **借鉴与吸收**:
  - 复用并优化了其多源行情接入与代码分类解析思路；
  - 针对国内网络环境完善了代理绕行与数据源降级瀑布链机制。

### 5. ricequant/rqalpha
- **来源代码库**: https://github.com/ricequant/rqalpha
- **许可证**: Apache 2.0 License
- **借鉴与吸收**:
  - 参考其关于 A 股交易费用标准（印花税减半、过户费率演进）、一字涨停无法买入、一字跌停无法卖出等撮合边界细节；
  - 本项目采用自包含纯 Python + SQLite 方案实现小资金与多标的共享资金池。

---

### 6. 数据源与基础设施组件
- **AKShare** (MIT License, https://github.com/akfamily/akshare): 沪深北实时与历史行情数据接口。
- **Baostock** (BSD License, http://baostock.com): 备用历史证券日线数据接口。
- **Streamlit** (Apache 2.0, https://streamlit.io): 现代金融交互界面引擎。
- **Plotly** (MIT License, https://plotly.com): 高保真交互式金融三合一 K 线与净值图表。
