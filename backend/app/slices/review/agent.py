"""合同智能审查 Agent（M2）的 AI 决策层。

流水线负责异步任务状态、文件文本化与报告落库；本 Agent 只负责条款提取、
法律依据/风险规则检索和风险分析。这样保留既有任务编排，又避免 AI 决策散落在
流水线的多个阶段中。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra import llm, vector
from app.models.knowledge import RiskRule
from app.slices.review import prompts

_RISK_LEVELS = {"high", "medium", "low"}
_SOURCE_TYPES = {"retrieved_law", "rule", "llm_inference"}


class ContractReviewAgent:
    """合同审查的正式业务 Agent。

    使用的 Tool 为：LLM（结构化条款与风险输出）、向量检索（RAG 法条候选）
    和 MySQL 风险规则查询。所有外部 AI 能力均经 ``app.infra`` 单点封装。
    """

    def extract_terms(self, text: str) -> dict[str, Any]:
        """调用结构化 LLM Tool 提取合同关键条款。"""
        result = llm.complete_structured(
            prompts.TERMS_SYSTEM,
            prompts.TERMS_USER_TEMPLATE.format(text=text[: prompts.MAX_TEXT_CHARS]),
            prompts.TERMS_SCHEMA,
        )
        return result if isinstance(result, dict) else {}

    async def retrieve(self, db: AsyncSession, *, terms: dict[str, Any], text: str) -> tuple[list[dict], list[RiskRule]]:
        """检索法条候选，并匹配确定性风险规则作为模型失效时的可解释兜底。"""
        query = " ".join(
            str(terms[key])
            for key in ("liability", "payment_terms", "amount", "jurisdiction")
            if terms.get(key)
        )
        legal_basis = [
            {"doc_id": hit.doc_id, "chunk_id": hit.chunk_id, "text": hit.text, "score": hit.score}
            for hit in vector.search(query or text[:200], top_k=5)
        ]
        rules = (await db.execute(select(RiskRule).where(RiskRule.is_active.is_(True), RiskRule.deleted_at.is_(None)))).scalars().all()
        matched = []
        for rule in rules:
            keywords = [item.strip() for item in (rule.match_keywords or "").split(",") if item.strip()]
            if keywords and any(keyword in text for keyword in keywords):
                matched.append(rule)
        return legal_basis, matched

    def analyze(self, *, terms: dict[str, Any], legal_basis: list[dict], rules: list[RiskRule], text: str) -> tuple[list[dict], list[dict]]:
        """基于检索上下文生成并规范化风险点，防止模型把推断冒充为法条依据。"""
        legal_basis_text = "\n".join(f"- {hit['text']}" for hit in legal_basis) or "（未检索到相关法条）"
        rules_text = "\n".join(
            f"- {rule.rule_code} {rule.name}：{rule.conclusion}（依据：{rule.legal_basis or '未标注'}）"
            for rule in rules
        ) or "（未命中审查规则）"
        result = llm.complete_structured(
            prompts.ANALYZE_SYSTEM,
            prompts.ANALYZE_USER_TEMPLATE.format(terms=terms, legal_basis=legal_basis_text, rules=rules_text, text=text[: prompts.MAX_TEXT_CHARS]),
            prompts.ANALYZE_SCHEMA,
        )
        raw_points = result.get("risk_points") if isinstance(result, dict) else []
        points = raw_points if isinstance(raw_points, list) else []
        return [self._normalize_point(point) for point in points if isinstance(point, dict)], points

    @staticmethod
    def _normalize_point(raw: dict[str, Any]) -> dict[str, Any]:
        """不可信来源降级为 ``llm_inference``，保证展示层不会误导用户。"""
        point = dict(raw)
        level = str(raw.get("risk_level") or "").strip().lower()
        source = str(raw.get("source_type") or "").strip().lower()
        point["risk_level"] = level if level in _RISK_LEVELS else "medium"
        point["source_type"] = source if source in _SOURCE_TYPES else "llm_inference"
        point["description"] = str(raw.get("description") or "模型未给出说明")
        return point
