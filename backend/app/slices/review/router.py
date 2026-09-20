"""审查切片的 HTTP 层。

只做三件事：解析请求 → 调用服务 → 包成统一响应体。
**业务规则不写在这里。**

⚠️ C-04 返回的是**二进制流**，不是统一响应体 —— 这是契约里唯一的例外
（05-接口设计 §5.4）。失败时仍走全局异常处理器，返回统一响应体。
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api import CurrentUserId, IdempotencyKey, RequestId, get_db
from app.core import idempotency
from app.core.errors import ApiResponse, Page
from app.slices.review import service
from app.slices.review.schemas import (
    CreateReviewRequest,
    DismissRiskPointRequest,
    ReviewListItem,
    ReviewResultData,
    ReviewTaskData,
    RiskPointData,
)

router = APIRouter(tags=["合同审查"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/reviews",
    response_model=ApiResponse[ReviewTaskData],
    status_code=status.HTTP_202_ACCEPTED,
    summary="C-01 发起合同审查（异步）",
)
def create_review(
    payload: CreateReviewRequest,
    background: BackgroundTasks,
    db: DbSession,
    user_id: CurrentUserId,
    idempotency_key: IdempotencyKey,
    rid: RequestId,
) -> ApiResponse[ReviewTaskData]:
    # 同一 Idempotency-Key 在 24 小时内重复提交，返回首次结果而不重复创建（§3.5）
    cached = idempotency.load(idempotency_key)
    if cached is not None:
        return ApiResponse.ok(ReviewTaskData(**cached), request_id=rid)

    data = service.create_task(db, user_id=user_id, payload=payload)
    db.commit()
    # 立即返回任务号，审查在响应发出后由后台线程执行（03-概要设计 §5.1）
    background.add_task(service.enqueue, int(data.task_id))
    idempotency.save(idempotency_key, data.model_dump())
    return ApiResponse.ok(data, request_id=rid)


@router.get(
    "/reviews",
    response_model=ApiResponse[Page[ReviewListItem]],
    summary="C-05 审查历史列表",
)
def list_reviews(
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
    page: int = Query(1),
    page_size: int = Query(20),
    status_filter: str | None = Query(None, alias="status"),
    sort: str = Query("-created_at"),
) -> ApiResponse[Page[ReviewListItem]]:
    items, total = service.list_tasks(
        db,
        user_id=user_id,
        page=page,
        page_size=page_size,
        status=status_filter,
        sort=sort,
    )
    return ApiResponse.ok(Page.of(items, page, page_size, total), request_id=rid)


@router.get(
    "/reviews/{task_id}",
    response_model=ApiResponse[ReviewTaskData],
    summary="C-02 查询审查任务状态",
)
def get_review(
    task_id: int, db: DbSession, user_id: CurrentUserId, rid: RequestId
) -> ApiResponse[ReviewTaskData]:
    return ApiResponse.ok(service.get_task(db, user_id=user_id, task_id=task_id), request_id=rid)


@router.get(
    "/reviews/{task_id}/result",
    response_model=ApiResponse[ReviewResultData],
    summary="C-03 获取审查结果",
)
def get_review_result(
    task_id: int, db: DbSession, user_id: CurrentUserId, rid: RequestId
) -> ApiResponse[ReviewResultData]:
    return ApiResponse.ok(service.get_result(db, user_id=user_id, task_id=task_id), request_id=rid)


@router.get("/reviews/{task_id}/report", summary="C-04 下载审查报告")
def download_review_report(task_id: int, db: DbSession, user_id: CurrentUserId, rid: RequestId) -> Response:
    filename, content = service.get_report(db, user_id=user_id, task_id=task_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            # filename*=UTF-8'' 用于中文文件名（RFC 5987）
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Request-ID": rid,
        },
    )


@router.patch(
    "/reviews/{task_id}/risk-points/{point_id}",
    response_model=ApiResponse[RiskPointData],
    summary="C-06 标记风险点为误报",
)
def dismiss_risk_point(
    task_id: int,
    point_id: int,
    payload: DismissRiskPointRequest,
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
) -> ApiResponse[RiskPointData]:
    data = service.dismiss_risk_point(
        db,
        user_id=user_id,
        task_id=task_id,
        point_id=point_id,
        is_dismissed=payload.is_dismissed,
    )
    db.commit()
    return ApiResponse.ok(data, request_id=rid)
