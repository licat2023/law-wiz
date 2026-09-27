"""最小 Internal API：只为 AI-Service Legal QA 检索提供受控数据。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import get_db
from app.api.deps import InternalService, RequestId
from app.core.errors import ApiResponse
from app.slices.kb import service
from app.slices.kb.schemas import KbSearchData

router = APIRouter(prefix="/internal", tags=["internal"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


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
