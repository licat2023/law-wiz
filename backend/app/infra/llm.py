"""LLM 能力的唯一封装。

⚠️ **外部能力单点封装**（见仓库根 AGENTS.md 硬性约束）：业务代码不得出现
任何厂商 SDK 的直接调用，一律通过本模块。

**与 AI 队友的接缝**：对方接入真实服务（`llm_provider=deepseek/ollama`）时
**只改本文件内部**，不得改动函数签名与错误行为 —— 业务代码只依赖本文件
声明的契约。

错误行为约定（业务代码必须按此处理，任务式接口应把任务标记为 `failed`
而不是把异常直接抛给用户）：
- 能力未接入（`llm_provider=stub`）→ `BusinessError(LLM_UNAVAILABLE)`；
- 已接入但返回无法解析 / 不满足 schema，重试 `llm_max_retries` 次后
  → `BusinessError(LLM_BAD_RESPONSE)`。

⚠️ **调用方请用「模块属性」写法**：

    from app.infra import llm
    llm.complete_structured(...)

**不要** `from app.infra.llm import complete_structured` —— 后者在 import 时
就把函数对象绑定进调用方命名空间，之后对模块的替换（测试 monkeypatch、
运行期切 provider）都不会对调用方生效。
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode

_settings = get_settings()


def complete_structured(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    """调用 LLM，要求返回符合 JSON Schema 的结构化数据。

    这是异步流水线（条款提取、风险分析、问答生成）中**唯一的** LLM 入口。
    """
    if _settings.llm_provider == "stub":
        raise BusinessError(ErrorCode.LLM_UNAVAILABLE, "AI 能力尚未接入，无法完成该步骤")
    if _settings.llm_provider == "fake":
        return _fake_response(schema)
    # 真实接入由 AI 队友实现；接入后此处应完成：构造请求 → 按 llm_max_retries
    # 重试解析 → 成功返回 dict，失败抛 BusinessError(LLM_BAD_RESPONSE)。
    raise BusinessError(ErrorCode.LLM_UNAVAILABLE, f"LLM 提供方 {_settings.llm_provider!r} 的实现尚未落地")


def _fake_response(schema: dict[str, Any]) -> dict[str, Any]:
    """开发/演示用的确定性占位结论。

    ⚠️ **不接入任何模型，结论是写死的** —— 它的唯一用途是让整条链路
    （流水线、状态机、报告生成、前端联调）在不接真实服务时可跑通。
    **生产环境由启动校验强制禁用**：假的风险结论比"暂时不可用"危险得多。

    按传入 schema 的形状返回对应结构，因此新增调用点时可能需要在此补一个分支。
    """
    properties = schema.get("properties", {})

    if "risk_points" in properties:
        return {
            "risk_points": [
                {
                    "risk_level": "high",
                    "risk_category": "legal",
                    "clause_title": "第八条 违约责任",
                    "clause_text": "乙方逾期交货的，应按合同总额的 30% 支付违约金。",
                    "char_start": 0,
                    "char_end": 24,
                    "description": "违约金比例过高，可能被法院认定为过分高于实际损失而予以调减。",
                    "suggestion": "建议将违约金比例调整至合同总额的 10%–20%，或约定以实际损失为基准计算。",
                    "legal_basis": "《中华人民共和国民法典》第五百八十五条",
                    "source_type": "retrieved_law",
                    "confidence": 0.86,
                },
                {
                    "risk_level": "medium",
                    "risk_category": "commercial",
                    "clause_title": "第五条 付款方式",
                    "clause_text": "验收合格后 30 日内付清。",
                    "description": "未约定验收标准与验收期限，可能导致付款条件无法确定。",
                    "suggestion": "补充验收标准、验收期限及逾期未验收视为通过的条款。",
                    "legal_basis": "《中华人民共和国民法典》第七百八十二条",
                    "source_type": "rule",
                    "confidence": None,
                },
                {
                    "risk_level": "low",
                    "risk_category": "compliance",
                    "description": "（演示占位）合同未约定通知与送达条款，争议时可能影响送达效力。",
                    "suggestion": "建议补充通知与送达条款，明确双方联系地址及电子送达方式。",
                    "source_type": "llm_inference",
                    "confidence": 0.42,
                },
            ]
        }

    if "answer" in properties:
        return {
            "answer": (
                "（演示占位）根据《中华人民共和国民法典》第五百八十五条，"
                "约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据"
                "当事人的请求予以适当减少。建议先与对方协商调整违约金比例。"
            ),
            # 引用第 1 条候选片段；若检索为空则对不上任何候选，
            # 上层会据此把 has_citation 置为 false —— 这正是"溯源不了要说出来"。
            "used_indexes": [1],
        }

    if "parties" in properties:
        return {
            "parties": ["甲方：某某科技有限公司", "乙方：某某贸易有限公司"],
            "amount": "人民币 120 万元",
            "payment_terms": "验收合格后 30 日内付清",
            "liability": "违约金按合同总额的 30% 计算",
            "jurisdiction": "合同签订地人民法院",
            "term": "2026-10-01 至 2027-09-30",
        }

    return {}
