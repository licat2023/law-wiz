"""最小 Internal API：只为 AI-Service Legal QA 检索提供受控数据。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import get_db
from app.api.deps import InternalService, RequestId
from app.core.errors import ApiResponse
from app.models.knowledge import RiskRule
from app.slices.kb import service
from app.slices.kb.schemas import KbSearchData

router = APIRouter(prefix="/internal", tags=["internal"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


class RiskRuleMatchRequest(BaseModel):
    """仅接收当前合同文本；不暴露合同、用户或任务 ORM 数据。"""

    plain_text: str = Field(min_length=1, max_length=12000)


@router.get("/legal-qa/laws", response_model=ApiResponse[KbSearchData])
async def retrieve_laws(
    _service: InternalService,
    db: DbSession,
    rid: RequestId,
    q: str = Query(min_length=1),
    top_k: int = Query(5, ge=1, le=20),
) -> ApiResponse[KbSearchData]:
    """仅返回现有 D-05 的结构化检索结果，不暴露 ORM/数据库。"""
    data = await service.search(
        db, query=q, top_k=top_k, doc_type=None, corpus_tier=None, include_abolished=False
    )
    return ApiResponse.ok(data, request_id=rid)


@router.post("/contract-review/risk-rules", response_model=ApiResponse[list[dict]])
async def match_risk_rules(
    payload: RiskRuleMatchRequest, _service: InternalService, db: DbSession, rid: RequestId
) -> ApiResponse[list[dict]]:
    """在 Backend 内匹配活跃规则，AI-Service 不直接读取业务数据库。"""
    rules = (
        (
            await db.execute(select(RiskRule).where(RiskRule.is_active.is_(True), RiskRule.deleted_at.is_(None)))
        )
        .scalars()
        .all()
    )
    items = []
    for rule in rules:
        keywords = [word.strip() for word in (rule.match_keywords or "").split(",") if word.strip()]
        if keywords and any(word in payload.plain_text for word in keywords):
            items.append(
                {
                    "risk_level": rule.risk_level,
                    "risk_category": rule.category,
                    "description": rule.conclusion,
                    "suggestion": rule.suggestion,
                    "legal_basis": rule.legal_basis,
                    "source_type": "rule",
                }
            )
    return ApiResponse.ok(items, request_id=rid)
