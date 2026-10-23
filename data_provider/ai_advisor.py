"""
可选 AI 智能解构与风险点评模块 (AI Advisor)
严格遵守安全与合规边界：
1. 纯可选增强：未配置大模型 API Key 时，所有交易、回测、筛选与风控功能 100% 完整运行；
2. 严禁编造虚假数据或宣称“上涨概率 80%”；
3. 明确区分【规则事实】与【AI 解读】；
4. 标明使用的模型、时间及分析数据范围。
"""

from datetime import datetime
import json
import os
from typing import Any, Dict, Optional


class AIAdvisor:
    """波段策略辅助解读与风险提示器"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self.is_configured = bool(self.api_key and len(self.api_key.strip()) > 5)

    def generate_stock_commentary(
        self,
        symbol: str,
        name: str,
        signal_data: Dict[str, Any],
        indicators_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        生成结构化解读与风险警示
        返回: {
            'is_llm_generated': bool,
            'model_name': str,
            'generated_at': str,
            'content': str,
            'disclaimer': str
        }
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not self.is_configured:
            # 离线启发式规则解读 (不依赖任何外部 API，稳定、严谨、零成本)
            strategy_name = signal_data.get("strategy_name", "波段策略")
            is_actionable = signal_data.get("is_actionable", False)
            conditions_met = signal_data.get("conditions_met", [])
            conditions_pending = signal_data.get("conditions_pending", [])
            risks = signal_data.get("risks", [])

            lines = [
                f"### 【波段技术面规则解构】 ({name} - {symbol})",
                f"- **策略模型**: {strategy_name}",
                f"- **当前决策状态**: {'【触发候选入场观察】' if is_actionable else '【暂无买入信号 / 等待条件形成】'}",
                "",
                "#### 一、已满足的确定性条件:",
            ]
            if conditions_met:
                for c in conditions_met:
                    lines.append(f"  -  {c}")
            else:
                lines.append("  - 暂无满足的核心条件")

            lines.append("\n#### 二、尚需等待的触发条件:")
            if conditions_pending:
                for p in conditions_pending:
                    lines.append(f"  - ⏳ {p}")
            else:
                lines.append("  - 全部关键技术条件均已触发")

            lines.append("\n#### 三、核心风险与应对备忘:")
            for r in risks:
                lines.append(f"  - ⚠️ {r}")

            lines.append(
                f"\n*数据基准日期: {signal_data.get('date', '最新交易日')} | 规则引擎分析版本: 1.0.0*"
            )

            return {
                "is_llm_generated": False,
                "model_name": "本地量化规则引擎 (无外部LLM依赖)",
                "generated_at": now_str,
                "content": "\n".join(lines),
                "disclaimer": "本内容由系统量化策略逻辑自动生成，不构成任何投资建议或收益保证。波段交易应以严格止损与资金管理为前提。",
            }

        # 若已配置大模型 API，则调用 OpenAI 兼容接口生成专业辅助研判
        try:
            import requests

            prompt = f"""你是一名严谨客观的 A 股证券分析助手。请根据以下量化规则事实，为标的 {name}({symbol}) 提供一份客观、不夸张、重在风险防范的简明交易备忘录：
策略名称: {signal_data.get('strategy_name')}
建议入场参考价: {signal_data.get('candidate_entry_price')}
建议止损位: {signal_data.get('stop_loss_price')} (依据: {signal_data.get('stop_loss_rationale')})
建议止盈位: {signal_data.get('take_profit_price')}
已满足条件: {json.dumps(signal_data.get('conditions_met', []), ensure_ascii=False)}
待满足条件: {json.dumps(signal_data.get('conditions_pending', []), ensure_ascii=False)}
已知风险: {json.dumps(signal_data.get('risks', []), ensure_ascii=False)}

要求：
1. 严格基于所给客观数据，禁止给出“上涨概率 XX%”或任何未经验证的保证；
2. 强调跳空低开、假突破和仓位控制风险；
3. 输出格式清晰排版为 Markdown。"""

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一名严谨的量化交易风险研究员。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
            }

            resp = requests.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return {
                    "is_llm_generated": True,
                    "model_name": self.model,
                    "generated_at": now_str,
                    "content": content,
                    "disclaimer": f"由 AI 模型 ({self.model}) 基于当时量化指标解读生成，仅供研究参考，不作为投资决策依据。",
                }
            else:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            # 降级为离线解读
            offline_result = self.generate_stock_commentary(symbol, name, signal_data, indicators_snapshot)
            offline_result["disclaimer"] += f" (外部大模型调用失败: {str(e)}，已自动降级为本地规则解读)"
            return offline_result

    def generate_portfolio_health_commentary(self, health_summary: Any) -> Dict[str, Any]:
        """为持仓组合体检生成客观风险解读"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 默认离线规则生成
        lines = [
            f"### 🛡️ 【持仓组合量化风控体检备忘】",
            f"- **体检时间**: {now_str}",
            f"- **组合综合评分**: {health_summary.overall_health_score:.1f} / 100 ({health_summary.overall_risk_rating})",
            f"- **持仓标的数**: {health_summary.positions_count} 只",
            f"- **第一重仓占比**: {health_summary.top_stock_weight_pct:.1f}%",
            f"- **浮动盈亏状态**: {health_summary.total_unrealized_pnl:+.2f} 元 ({health_summary.total_pnl_pct*100:+.2f}%)",
            "",
            "#### 一、核心风险预警清单:",
        ]
        if health_summary.system_alerts:
            for alert in health_summary.system_alerts:
                lines.append(f"  - ⚠️ {alert}")
        else:
            lines.append("  - ✅ 组合目前未触发集中度超标或大幅回撤警报")

        lines.append("\n#### 二、调仓与止损建议依据:")
        high_risk_positions = [p for p in health_summary.detailed_positions if p.risk_level == "HIGH"]
        if high_risk_positions:
            for p in high_risk_positions:
                lines.append(f"  - **{p.name}({p.symbol})**: 浮亏 {p.pnl_pct*100:.1f}%，走势处于【{p.trend_status}】，建议参考止损位 {p.suggested_stop_loss:.2f} 元执行纪律减仓。")
        else:
            lines.append("  - 目前各持仓标的均在正常波段波动区间，请继续跟踪移动止损位。")

        return {
            "is_llm_generated": False,
            "model_name": "本地因果规则引擎 (严守风控准则)",
            "generated_at": now_str,
            "content": "\n".join(lines),
            "disclaimer": "持仓体检基于历史客观数据与量化风控模型计算，不构成交易建议。严守止损纪律是控制波段风险的第一道防线。",
        }

