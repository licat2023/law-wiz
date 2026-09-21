"""知识库切片的 HTTP 层。

只做三件事：解析请求 → 调用服务 → 包成统一响应体。
**业务规则不写在这里。**

⚠️ **D 组全部要求登录**。文档中 D-01 与 D-03 的错误码未列 `40101`，
但 `kb_document` 表没有任何归属字段，说明语料是**平台级**数据而非用户私有 ——
这类写操作更不应匿名开放。此处统一要求鉴权，属于对文档疏漏的补齐（已记入手记）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.api import CurrentUserId, RateLimitedAI, RateLimitedRead, RequestId, get_db
from app.core.errors import ApiResponse, Page
from app.slices.kb import service
from app.slices.kb.schemas import (
    CreateDocumentRequest,
    DocumentCreatedData,
    DocumentDetailData,
    DocumentListItem,
    IndexRequest,
    IndexTriggeredData,
    KbSearchData,
)

router = APIRouter(tags=["法律知识库"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/kb/documents",
    response_model=ApiResponse[DocumentCreatedData],
    status_code=status.HTTP_201_CREATED,
    summary="D-01 创建语料元数据",
)
def create_document(
    payload: CreateDocumentRequest,
    db: DbSession,
    _user: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedRead,
) -> ApiResponse[DocumentCreatedData]:
    data = service.create_document(db, payload)
    db.commit()
    return ApiResponse.ok(data, request_id=rid)


@router.post(
    "/kb/documents/{document_id}/index",
    response_model=ApiResponse[IndexTriggeredData],
    status_code=status.HTTP_202_ACCEPTED,
    summary="D-02 触发向量化索引（异步）",
)
def trigger_index(
    document_id: int,
    background: BackgroundTasks,
    db: DbSession,
    _user: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedAI,
    payload: Annotated[IndexRequest | None, Body()] = None,
) -> ApiResponse[IndexTriggeredData]:
    data = service.trigger_index(db, document_id=document_id, force=payload.force if payload else False)
    db.commit()
    background.add_task(service.enqueue, int(data.document_id))
    return ApiResponse.ok(data, request_id=rid)


@router.get(
    "/kb/documents",
    response_model=ApiResponse[Page[DocumentListItem]],
    summary="D-03 语料列表",
)
def list_documents(
    db: DbSession,
    _user: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedRead,
    page: int = Query(1),
    page_size: int = Query(20),
    doc_type: str | None = Query(None),
    corpus_tier: int | None = Query(None),
    index_status: str | None = Query(None),
    law_name: str | None = Query(None),
    sort: str = Query("-created_at"),
) -> ApiResponse[Page[DocumentListItem]]:
    items, total = service.list_documents(
        db,
        page=page,
        page_size=page_size,
        doc_type=doc_type,
        corpus_tier=corpus_tier,
        index_status=index_status,
        law_name=law_name,
        sort=sort,
    )
    return ApiResponse.ok(Page.of(items, page, page_size, total), request_id=rid)


@router.get(
    "/kb/documents/{document_id}",
    response_model=ApiResponse[DocumentDetailData],
    summary="D-04 语料详情",
)
def get_document(
    document_id: int,
    db: DbSession,
    _user: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedRead,
) -> ApiResponse[DocumentDetailData]:
    return ApiResponse.ok(service.get_document(db, document_id), request_id=rid)


@router.get(
    "/kb/search",
    response_model=ApiResponse[KbSearchData],
    summary="D-05 语义检索",
)
def search(
    db: DbSession,
    _user: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedRead,
    q: str = Query(description="检索文本"),
    top_k: int = Query(5),
    doc_type: str | None = Query(None),
    corpus_tier: int | None = Query(None),
    include_abolished: bool = Query(False),
) -> ApiResponse[KbSearchData]:
    data = service.search(
        db,
        query=q,
        top_k=top_k,
        doc_type=doc_type,
        corpus_tier=corpus_tier,
        include_abolished=include_abolished,
    )
    return ApiResponse.ok(data, request_id=rid)
