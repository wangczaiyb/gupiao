# 开源项目采用与第三方声明 (Third-Party Notices)

本项目在调研与架构设计过程中参考并评估了开源项目：

### 1. ZhuLinsen/daily_stock_analysis
- 来源代码库: https://github.com/ZhuLinsen/daily_stock_analysis
- 许可证: MIT License (Copyright (c) 2026 ZhuLinsen)
- 调研版本 / Commit: `ec66bf46caf6993f673bd4be59c883754667b686`
- 评估说明:
  - 上游项目主要定位为“基于 AI 大模型的跨市场日报生成与消息机器人推送”，包含庞大的 FastAPI + React/Vite 桌面/网页系统，强依赖外部 LLM API 与复杂的前端构建链。
  - 缺乏针对 A 股全市场（主板/创业板/科创板/北交所）的波段量化策略引擎、严格 T+1 回测计算、分板块申报与费率规则、跳空止损与模拟盘账本管理。
  - 为满足用户“轻量启动、无需繁琐配置、电脑手机均便携、低维护成本、专注波段策略与可复现回测”的核心目标，本项目采用了上游所验证的多源行情接入思想与代码解析模式，使用 Python + Streamlit + Plotly + SQLite 进行了轻量、自包含、高可复现的全新独立实现，避免引入无意义的重型微服务与代理系统。

### 2. AKShare
- 来源: https://github.com/akfamily/akshare
- 许可证: MIT License
- 用途: 获取沪深北 A 股日线行情与实时行情快照。

### 3. Baostock
- 来源: http://baostock.com
- 许可证: BSD License
- 用途: 提供备用证券历史行情数据。

### 4. Streamlit & Plotly
- Streamlit (Apache 2.0), Plotly (MIT)
- 用途: 交互式行情图表、波段分析看板与回测结果展示。
