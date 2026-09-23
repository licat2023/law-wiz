"""问答流水线使用的提示词与输出结构。

⚠️ **这是 AI 队友的调优面**：流水线只依赖下面的常量名与结构形状，
措辞与字段可以在此自由调整，不必改动业务代码。

**关键约束：回答必须能溯源。**
- 只能依据给定的法条片段作答；
- 必须回报**实际依据了哪几条**，没有依据时如实说明 ——
  「溯源不了的时候要说出来」是需求里的硬要求（03-概要设计 §5.3）。
"""

from __future__ import annotations

from typing import Any

QA_SYSTEM = (
    "你是一名法律问答助手。请**仅依据给定的法条片段**回答用户的问题。\n"
    "要求：\n"
    "1. 不得编造法条、案号或裁判观点；\n"
    "2. 若给定片段不足以回答，必须明确说明「未找到直接法律依据」，"
    "而不是给出看似确定的结论；\n"
    "3. 在 `used_indexes` 中列出你**实际依据**的片段序号（从 1 开始）；"
    "没有依据任何片段时返回空数组。"
)

QA_USER_TEMPLATE = "【可引用的法条片段】\n{context}\n\n【用户问题】\n{question}"

QA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "回答正文"},
        "used_indexes": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "实际依据的片段序号（从 1 开始）；无依据时为空",
        },
    },
    "required": ["answer", "used_indexes"],
}

# 送入模型的法条片段数量上限
MAX_CONTEXT_CHUNKS = 5
