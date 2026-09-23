"""问答切片的 HTTP 层。

只做三件事：解析请求 → 调用服务 → 包成统一响应体。
**业务规则不写在这里。**
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import (
    CurrentUserId,
    IdempotencyKey,
    RateLimitedAI,
    RateLimitedPoll,
    RateLimitedRead,
    RequestId,
    get_db,
)
from app.core import idempotency
from app.core.errors import ApiResponse, Page
from app.slices.qa import service
from app.slices.qa.schemas import (
    AskData,
    AskRequest,
    CreateSessionRequest,
    SessionData,
    SessionDetailData,
    SessionListItem,
)

router = APIRouter(tags=["法律问答"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "/qa/sessions",
    response_model=ApiResponse[SessionData],
    status_code=status.HTTP_201_CREATED,
    summary="E-01 创建问答会话",
)
async def create_session(
    payload: CreateSessionRequest,
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedRead,
) -> ApiResponse[SessionData]:
    data = await service.create_session(db, user_id=user_id, payload=payload)
    await db.commit()
    return ApiResponse.ok(data, request_id=rid)


@router.get(
    "/qa/sessions",
    response_model=ApiResponse[Page[SessionListItem]],
    summary="E-02 会话列表",
)
async def list_sessions(
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedRead,
    page: int = Query(1),
    page_size: int = Query(20),
    status_filter: str | None = Query(None, alias="status"),
    sort: str = Query("-last_message_at"),
) -> ApiResponse[Page[SessionListItem]]:
    items, total = await service.list_sessions(
        db,
        user_id=user_id,
        page=page,
        page_size=page_size,
        status=status_filter,
        sort=sort,
    )
    return ApiResponse.ok(Page.of(items, page, page_size, total), request_id=rid)


@router.get(
    "/qa/sessions/{session_id}",
    response_model=ApiResponse[SessionDetailData],
    summary="E-03 会话详情（含消息与引用）",
)
async def get_session(
    session_id: int,
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedPoll,
    page: int = Query(1),
    page_size: int = Query(20),
) -> ApiResponse[SessionDetailData]:
    data = await service.get_session(
        db, user_id=user_id, session_id=session_id, page=page, page_size=page_size
    )
    return ApiResponse.ok(data, request_id=rid)


@router.post(
    "/qa/sessions/{session_id}/messages",
    response_model=ApiResponse[AskData],
    status_code=status.HTTP_202_ACCEPTED,
    summary="E-04 提问（异步）",
)
async def ask(
    session_id: int,
    payload: AskRequest,
    background: BackgroundTasks,
    db: DbSession,
    user_id: CurrentUserId,
    idempotency_key: IdempotencyKey,
    rid: RequestId,
    _rate: RateLimitedAI,
) -> ApiResponse[AskData]:
    # 同一 Idempotency-Key 在 24 小时内重复提交，返回首次结果而不重复提问（§3.5）
    cached = await idempotency.load("qa", idempotency_key)
    if cached is not None:
        return ApiResponse.ok(AskData(**cached), request_id=rid)

    data = await service.ask(db, user_id=user_id, session_id=session_id, content=payload.content)
    await db.commit()
    # 立即返回两个消息 ID，回答由后台任务生成（03-概要设计 §5.1）
    background.add_task(
        service.enqueue,
        message_id=int(data.assistant_message_id),
        session_id=session_id,
    )
    await idempotency.save("qa", idempotency_key, data.model_dump())
    return ApiResponse.ok(data, request_id=rid)


@router.delete(
    "/qa/sessions/{session_id}",
    response_model=ApiResponse[None],
    summary="E-05 归档会话",
)
async def archive_session(
    session_id: int,
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedRead,
) -> ApiResponse[None]:
    await service.archive(db, user_id=user_id, session_id=session_id)
    await db.commit()
    return ApiResponse.ok(None, request_id=rid)
