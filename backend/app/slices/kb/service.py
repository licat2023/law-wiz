"""知识库业务逻辑（M3 的 D 组）。

**服务层不依赖 HTTP**：接收普通参数、抛 `BusinessError`、返回普通对象。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import to_iso
from app.core.errors import BusinessError, ErrorCode
from app.infra.storage import sha256_of
from app.models.knowledge import KbChunk, KbDocument
from app.slices.kb import chunking
from app.slices.kb.pipeline import STATUS_PENDING, run_index_pipeline
from app.slices.kb.schemas import (
    ChunkItem,
    CreateDocumentRequest,
    DocumentCreatedData,
    DocumentDetailData,
    DocumentListItem,
    IndexTriggeredData,
    KbSearchData,
    KbSearchItem,
)

_MAX_PAGE_SIZE = 100
_DETAIL_CHUNK_LIMIT = 20
_MAX_TOP_K = 20

_SORT_OPTIONS = {
    "-created_at": KbDocument.created_at.desc(),
    "created_at": KbDocument.created_at.asc(),
    "-effective_date": KbDocument.effective_date.desc(),
    "effective_date": KbDocument.effective_date.asc(),
}


async def _chunk_count(db: AsyncSession, document_id: int) -> int:
    count = await db.scalar(
        select(func.count()).select_from(KbChunk).where(KbChunk.kb_document_id == document_id)
    )
    return count or 0


# ============================================================
# D-01 创建语料
# ============================================================


async def create_document(db: AsyncSession, payload: CreateDocumentRequest) -> DocumentCreatedData:
    """创建语料，**并立即切分落块**。

    切分放在这里而不是索引阶段，是因为 `kb_document` 不存全文 ——
    分块是全文的唯一载体；若创建时不落块，索引阶段就无据可切。
    """
    content = payload.content
    digest = await asyncio.to_thread(sha256_of, content.encode("utf-8"))

    existing = await db.scalar(
        select(KbDocument.id).where(KbDocument.content_hash == digest, KbDocument.deleted_at.is_(None))
    )
    if existing is not None:
        raise BusinessError(ErrorCode.KB_DOC_EXISTS, "相同内容的语料已存在")

    document = KbDocument(
        doc_type=payload.doc_type,
        corpus_tier=payload.corpus_tier,
        title=payload.title,
        law_name=payload.law_name,
        article_no=payload.article_no,
        chapter_path=payload.chapter_path,
        effective_date=payload.effective_date,
        abolished_date=payload.abolished_date,
        revision=payload.revision,
        source=payload.source,
        source_url=payload.source_url,
        content_hash=digest,
        char_count=len(content),
        index_status=STATUS_PENDING,
    )
    db.add(document)
    await db.flush()

    chunks = chunking.split_into_chunks(content)
    # 分块冗余 `law_name` / `effective_date` 是**刻意的反范式**（04-数据库设计 §5.10）：
    # 检索命中后要立刻给出可读引用、并按生效日期过滤已废止法条，每次回表会明显增加延迟。
    for chunk in chunks:
        db.add(
            KbChunk(
                kb_document_id=document.id,
                chunk_no=chunk.chunk_no,
                chunk_type=chunk.chunk_type,
                article_no=chunk.article_no or payload.article_no,
                law_name=payload.law_name,
                effective_date=payload.effective_date,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
        )
    await db.flush()

    return DocumentCreatedData(
        document_id=str(document.id),
        content_hash=digest,
        char_count=len(content),
        index_status=document.index_status,
        chunk_count=len(chunks),
    )


# ============================================================
# D-02 触发索引
# ============================================================


async def trigger_index(db: AsyncSession, *, document_id: int, force: bool) -> IndexTriggeredData:
    document = await _load_document(db, document_id)

    if not force and document.index_status == "indexing":
        # 已在索引中且未要求强制重建：原样返回当前状态，不重复触发
        return _to_triggered(document)

    document.index_status = STATUS_PENDING
    await db.flush()
    return _to_triggered(document)


def _to_triggered(document: KbDocument) -> IndexTriggeredData:
    return IndexTriggeredData(
        document_id=str(document.id),
        index_status=document.index_status,
        # 没有索引任务表，索引以文档为单位，任务标识即文档标识
        task_id=str(document.id),
    )


async def enqueue(document_id: int) -> None:
    """登记并执行索引任务。

    单独成函数是为了**让测试可以替换它** —— 测试里不应真的跑向量化。
    """
    await run_index_pipeline(document_id)


# ============================================================
# D-03 语料列表
# ============================================================


async def list_documents(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    doc_type: str | None,
    corpus_tier: int | None,
    index_status: str | None,
    law_name: str | None,
    sort: str,
) -> tuple[list[DocumentListItem], int]:
    if page < 1 or page_size < 1 or page_size > _MAX_PAGE_SIZE:
        raise BusinessError(
            ErrorCode.PAGE_OUT_OF_RANGE, f"分页参数超出范围（page_size 上限 {_MAX_PAGE_SIZE}）"
        )
    order_by = _SORT_OPTIONS.get(sort)
    if order_by is None:
        raise BusinessError(ErrorCode.PARAM_INVALID, "sort 取值不合法")

    conditions = [KbDocument.deleted_at.is_(None)]
    if doc_type is not None:
        conditions.append(KbDocument.doc_type == doc_type)
    if corpus_tier is not None:
        conditions.append(KbDocument.corpus_tier == corpus_tier)
    if index_status is not None:
        conditions.append(KbDocument.index_status == index_status)
    if law_name:
        conditions.append(KbDocument.law_name.like(f"%{law_name}%"))

    total = await db.scalar(select(func.count()).select_from(KbDocument).where(*conditions)) or 0
    documents = (
        (
            await db.execute(
                select(KbDocument)
                .where(*conditions)
                .order_by(order_by)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return [await _to_list_item(db, doc) for doc in documents], int(total)


async def _to_list_item(db: AsyncSession, document: KbDocument) -> DocumentListItem:
    return DocumentListItem(
        document_id=str(document.id),
        doc_type=document.doc_type,
        corpus_tier=document.corpus_tier,
        title=document.title,
        law_name=document.law_name,
        article_no=document.article_no,
        effective_date=document.effective_date.isoformat() if document.effective_date else None,
        index_status=document.index_status,
        chunk_count=await _chunk_count(db, document.id),
        created_at=to_iso(document.created_at) or "",
    )


# ============================================================
# D-04 语料详情
# ============================================================


async def get_document(db: AsyncSession, document_id: int) -> DocumentDetailData:
    document = await _load_document(db, document_id)
    chunks = (
        (
            await db.execute(
                select(KbChunk).where(KbChunk.kb_document_id == document.id).order_by(KbChunk.chunk_no)
            )
        )
        .scalars()
        .all()
    )

    return DocumentDetailData(
        document_id=str(document.id),
        doc_type=document.doc_type,
        corpus_tier=document.corpus_tier,
        title=document.title,
        law_name=document.law_name,
        article_no=document.article_no,
        chapter_path=document.chapter_path,
        effective_date=document.effective_date.isoformat() if document.effective_date else None,
        abolished_date=document.abolished_date.isoformat() if document.abolished_date else None,
        revision=document.revision,
        source=document.source,
        source_url=document.source_url,
        content_hash=document.content_hash,
        char_count=document.char_count,
        index_status=document.index_status,
        indexed_at=to_iso(document.indexed_at),
        chunk_count=len(chunks),
        created_at=to_iso(document.created_at) or "",
        # ⚠️ 全文不单独存储，只能由分块按序拼接**重建** —— 分块之间的空白不可还原，
        # 因此重建结果与原文可能有细微差异。需要逐字原文时应改用分块的 char_start/char_end。
        content="\n".join(chunk.content for chunk in chunks),
        chunks=[
            ChunkItem(
                chunk_no=chunk.chunk_no,
                chunk_type=chunk.chunk_type,
                article_no=chunk.article_no,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                content=chunk.content,
            )
            for chunk in chunks[:_DETAIL_CHUNK_LIMIT]
        ],
    )


async def _load_document(db: AsyncSession, document_id: int) -> KbDocument:
    document = await db.get(KbDocument, document_id)
    if document is None or document.deleted_at is not None:
        raise BusinessError(ErrorCode.KB_DOC_NOT_FOUND, "语料不存在")
    return document


# ============================================================
# D-05 语义检索
# ============================================================


async def search(
    db: AsyncSession,
    *,
    query: str,
    top_k: int,
    doc_type: str | None,
    corpus_tier: int | None,
    include_abolished: bool,
) -> KbSearchData:
    if not query.strip():
        raise BusinessError(ErrorCode.PARAM_INVALID, "检索文本不能为空")
    if top_k < 1 or top_k > _MAX_TOP_K:
        raise BusinessError(ErrorCode.PARAM_INVALID, f"top_k 取值范围为 1–{_MAX_TOP_K}")

    from app.infra import vector

    # 多取一些候选：过滤（类型/分级/废止）会淘汰一部分，取少了会凑不满 top_k
    # ⚠️ 检索是 CPU 密集调用（内存后端要遍历全部向量）：过 `asyncio.to_thread`，
    # 否则检索期间整个事件循环都被占住。
    hits = await asyncio.to_thread(vector.search, query, min(top_k * 5, 100))
    if not hits:
        return KbSearchData(query=query, items=[])

    chunk_ids = [int(hit.chunk_id) for hit in hits if hit.chunk_id.isdigit()]
    chunks = {
        chunk.id: chunk
        for chunk in (await db.execute(select(KbChunk).where(KbChunk.id.in_(chunk_ids)))).scalars().all()
    }
    document_ids = {chunk.kb_document_id for chunk in chunks.values()}
    documents = {
        document.id: document
        for document in (await db.execute(select(KbDocument).where(KbDocument.id.in_(document_ids))))
        .scalars()
        .all()
    }

    items: list[KbSearchItem] = []
    for hit in hits:
        if not hit.chunk_id.isdigit():
            continue
        chunk = chunks.get(int(hit.chunk_id))
        if chunk is None:
            continue
        document = documents.get(chunk.kb_document_id)
        if document is None or document.deleted_at is not None:
            continue
        if doc_type is not None and document.doc_type != doc_type:
            continue
        if corpus_tier is not None and document.corpus_tier != corpus_tier:
            continue
        # 默认排除已废止法条：据以作答是本项目最严重的失败形态之一（05-接口设计 §5.5）
        if not include_abolished and document.abolished_date is not None:
            continue

        items.append(
            KbSearchItem(
                chunk_id=str(chunk.id),
                document_id=str(document.id),
                # 优先取分块上的冗余字段（检索路径不回表，见 04-数据库设计 §5.10）
                law_name=chunk.law_name or document.law_name,
                article_no=chunk.article_no or document.article_no,
                chunk_type=chunk.chunk_type,
                content=chunk.content,
                effective_date=(chunk.effective_date or document.effective_date).isoformat()
                if (chunk.effective_date or document.effective_date)
                else None,
                score=hit.score,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
        )
        if len(items) >= top_k:
            break

    return KbSearchData(query=query, items=items)
