"""索引建立、任务查询及检索块查看的 HTTP 入口。"""

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app.api.deps import Db, Key, User
from app.api.responses import Envelope, ok
from app.api.responses import page as paginate
from app.documents.models import Document
from app.documents.service import load_document
from app.errors import AppError
from app.indexing.chunking import ChunkOptions
from app.indexing.models import Chunk, IndexRevision, ProcessingJob
from app.indexing.schemas import IndexRequest
from app.indexing.service import add_job, chunk_view, job_view
from app.infrastructure.idempotency import digest, idempotent
from app.knowledge_bases.service import load_kb

router = APIRouter(prefix="/api")


@router.post(
    "/knowledge-bases/{kb_id}/documents/{document_id}/indexes", response_model=Envelope[dict], status_code=202
)
async def index_document(
    kb_id: str,
    document_id: str,
    payload: IndexRequest,
    request: Request,
    db: Db,
    user: User,
    idempotency_key: Key = None,
):
    user.require_write()
    kb = await load_kb(db, user, kb_id)

    async def action():
        doc = await load_document(db, kb, document_id)
        if doc.revision != payload.revision:
            raise AppError(40901, "文档已更新，请刷新后重试", 409)
        options = ChunkOptions.model_validate(
            kb.options | payload.model_dump(exclude_none=True, exclude={"revision"})
        )
        return job_view(await add_job(db, doc, options.model_dump()))

    result = await idempotent(
        db,
        user,
        f"{kb_id}:{document_id}:index",
        idempotency_key,
        digest(payload.model_dump()),
        action,
    )
    await db.commit()
    return ok(request, result)


@router.get("/knowledge-bases/{kb_id}/documents/{document_id}/chunks", response_model=Envelope[dict])
async def chunks(
    kb_id: str,
    document_id: str,
    request: Request,
    db: Db,
    user: User,
    index_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    kb = await load_kb(db, user, kb_id)
    doc = await load_document(db, kb, document_id)
    index = (
        await db.get(IndexRevision, index_id or doc.active_index_id)
        if index_id or doc.active_index_id
        else None
    )
    if index is None:
        return ok(request, paginate([], 0, page, page_size))
    if index.document_id != doc.id:
        raise AppError(40403, "索引不存在", 404)
    total = await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.index_id == index.id))
    rows = (
        await db.scalars(
            select(Chunk)
            .where(Chunk.index_id == index.id)
            .order_by(Chunk.chunk_no)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return ok(request, paginate([chunk_view(c) for c in rows], total, page, page_size))


@router.get("/jobs/{job_id}", response_model=Envelope[dict])
async def job(job_id: str, request: Request, db: Db, user: User):
    job = await db.get(ProcessingJob, job_id)
    if job is None:
        raise AppError(40404, "处理任务不存在", 404)
    doc = await db.get(Document, job.document_id)
    await load_kb(db, user, doc.knowledge_base_id)
    return ok(request, job_view(job))
