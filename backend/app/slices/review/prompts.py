"""审查流水线使用的提示词与输出结构。

⚠️ **这是 AI 队友的调优面。** 流水线只依赖下面的**常量名**与结构形状；
提示词措辞、few-shot 示例、字段增删都可以在此自由调整，**不必改动业务代码**。

单独成文件的理由：提示词是"模型表现"的调优对象，会反复修改；若散落在流水线
逻辑里，每次调优都要改业务代码，也会让 review 的 diff 混杂无关噪音。
"""

from __future__ import annotations

from typing import Any

# ============================================================
# 第一步：关键条款提取（M2-03）
# ============================================================

TERMS_SYSTEM = (
    "你是一名合同信息抽取助手。请从用户给出的合同全文中提取约定要素，"
    "严格按给定 JSON 结构返回。"
    "**不得推测原文没有的内容**：原文未提及的字段返回 null，不要编造。"
)

TERMS_USER_TEMPLATE = "合同全文如下：\n\n{text}"

TERMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "parties": {
            "type": "array",
            "items": {"type": "string"},
            "description": "合同各方，如「甲方：某某公司」",
        },
        "amount": {"type": "string", "description": "合同金额，原文表述"},
        "payment_terms": {"type": "string", "description": "付款条款"},
        "liability": {"type": "string", "description": "违约责任条款"},
        "jurisdiction": {"type": "string", "description": "争议解决 / 管辖约定"},
        "term": {"type": "string", "description": "合同期限"},
    },
    "required": ["parties"],
}


# ============================================================
# 第二步：风险分析（M2-05）
# ============================================================

ANALYZE_SYSTEM = (
    "你是一名合同风险审查助手。请结合合同条款与给定的法律依据，指出其中的法律、"
    "商务与合规风险。\n"
    "**必须如实标注每条风险的依据来源**（source_type）：\n"
    "- retrieved_law：结论直接依据下方检索到的法条；\n"
    "- rule：结论依据下方给出的人工审查规则；\n"
    "- llm_inference：基于常识推断、**没有直接法律依据**。\n"
    "宁可标注为 llm_inference，也不要把推断包装成法条依据。\n"
    "char_start / char_end 请给出条款在**合同原文**中的字符偏移；无法确定时返回 null。"
)

ANALYZE_USER_TEMPLATE = (
    "【合同条款要素】\n{terms}\n\n"
    "【检索到的法律依据】\n{legal_basis}\n\n"
    "【命中的审查规则】\n{rules}\n\n"
    "【合同原文（节选）】\n{text}"
)

ANALYZE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "risk_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk_level": {"type": "string", "enum": ["high", "medium", "low"]},
                    "risk_category": {"type": "string", "description": "legal / commercial / compliance"},
                    "clause_title": {"type": "string"},
                    "clause_text": {"type": "string"},
                    "char_start": {"type": ["integer", "null"]},
                    "char_end": {"type": ["integer", "null"]},
                    "description": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "legal_basis": {"type": "string"},
                    "source_type": {
                        "type": "string",
                        "enum": ["retrieved_law", "rule", "llm_inference"],
                    },
                    "confidence": {"type": ["number", "null"]},
                },
                "required": ["risk_level", "description", "source_type"],
            },
        }
    },
    "required": ["risk_points"],
}

# 原文送入模型的最大字符数：控制单次请求的 token 与耗时
MAX_TEXT_CHARS = 12000
