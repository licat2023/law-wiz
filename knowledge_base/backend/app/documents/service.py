"""创建、修订、删除与读取知识库文档。"""

import asyncio
import json

from sqlalchemy import func, select, update

from app.api.responses import page
from app.documents.models import Document, DocumentRevision
from app.documents.parsing import extract_document
from app.errors import AppError, invalid
from app.indexing.models import IndexRevision, ProcessingJob
from app.indexing.service import add_job, job_view
from app.infrastructure.database import now
from app.infrastructure.idempotency import digest
from app.infrastructure.storage import write_file


async def load_document(db, kb, document_id):
    doc = await db.get(Document, document_id)
    if doc is None or doc.knowledge_base_id != kb.id or doc.deleted_at is not None:
        raise AppError(40402, "文档不存在或已删除", 404)
    return doc


async def revision_of(db, document_id, number):
    return await db.scalar(
        select(DocumentRevision).where(
            DocumentRevision.document_id == document_id, DocumentRevision.number == number
        )
    )


async def document_view(db, doc, *, detail=False):
    result = {
        key: getattr(doc, key)
        for key in (
            "id",
            "knowledge_base_id",
            "title",
            "filename",
            "format",
            "revision",
            "status",
            "active_index_id",
            "chunk_count",
            "error_message",
        )
    } | {
        "metadata": doc.source_metadata,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }
    if detail:
        revision = await revision_of(db, doc.id, doc.revision)
        current_job_id = None
        if doc.desired_index_id is not None:
            current_job_id = await db.scalar(
                select(ProcessingJob.id).where(
                    ProcessingJob.document_id == doc.id,
                    ProcessingJob.revision == doc.revision,
                    ProcessingJob.index_id == doc.desired_index_id,
                    ProcessingJob.status.in_(("pending", "processing")),
                )
            )
        jobs = (
            await db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == doc.id)
                .order_by(ProcessingJob.created_at.desc())
                .limit(20)
            )
        ).all()
        indexes = (
            await db.scalars(
                select(IndexRevision)
                .where(IndexRevision.document_id == doc.id)
                .order_by(IndexRevision.created_at.desc())
                .limit(50)
            )
        ).all()
        result |= {
            "content": revision.content or "",
            "current_job_id": current_job_id,
            "jobs": [job_view(j) for j in jobs],
            "indexes": [
                {"id": i.id, "revision": i.revision, "status": i.status, "options": i.options}
                for i in indexes
            ],
        }
    return result


def validate_metadata(metadata):
    if len(json.dumps(metadata, ensure_ascii=False)) > 65536:
        raise invalid("文档元数据超过长度上限")
    for field in ("effective_date", "abolished_date"):
        if metadata.get(field):
            from datetime import date

            try:
                date.fromisoformat(str(metadata[field]))
            except ValueError as exc:
                raise invalid(f"{field} 需使用 YYYY-MM-DD") from exc


async def markdown_content(state, body, *, empty_recovery):
    if empty_recovery:
        return "", []
    parsed = await asyncio.to_thread(
        extract_document, body, "document.md", max_chars=state.settings.max_text_chars
    )
    return parsed.text, parsed.block_data()


def mark_empty_recovery(doc):
    doc.status = "failed"
    doc.error_message = "旧文档没有可恢复的正文，补录正文后可建立索引"
    doc.desired_index_id = None


async def create_document(
    db, state, kb, title, filename, fmt, body, metadata, *, content=None, deleted=False, empty_recovery=False
):
    title = title.strip()
    if not title or len(title) > 300:
        raise invalid("标题需为 1–300 字符")
    validate_metadata(metadata)
    text, blocks = None, None
    if content is not None:
        text, blocks = await markdown_content(state, body, empty_recovery=empty_recovery)
    file_key = None if deleted or empty_recovery else await write_file(state, body)
    doc = Document(
        knowledge_base_id=kb.id, title=title, filename=filename[:300], format=fmt, source_metadata=metadata
    )
    if deleted:
        doc.deleted_at = now()
        doc.status = "deleted"
    elif empty_recovery:
        mark_empty_recovery(doc)
    db.add(doc)
    await db.flush()
    db.add(
        DocumentRevision(
            document_id=doc.id,
            number=1,
            filename=doc.filename,
            format=fmt,
            file_key=file_key,
            content_hash=digest(body),
            source_metadata=metadata,
            content=text,
            blocks=blocks,
        )
    )
    if not deleted and not empty_recovery:
        await add_job(db, doc, kb.options)
    return await document_view(db, doc)


async def change_document(
    db,
    state,
    kb,
    doc,
    expected_revision,
    *,
    title=None,
    metadata=None,
    content=None,
    file_body=None,
    filename=None,
    fmt=None,
    deleted=False,
    empty_recovery=False,
):
    if doc.revision != expected_revision:
        raise AppError(40901, "文档已更新，请刷新后重试", 409)
    old = await revision_of(db, doc.id, doc.revision)
    if title is not None and not title.strip():
        raise invalid("标题不能为空")
    if content is not None and doc.format != "markdown":
        raise invalid("PDF 和 Word 请通过替换文件修改正文")
    next_metadata = metadata if metadata is not None else doc.source_metadata
    validate_metadata(next_metadata)
    next_file_key = old.file_key
    next_content, next_blocks, next_hash = old.content, old.blocks, old.content_hash
    if content is not None:
        body = content.encode("utf-8")
        next_content, next_blocks = await markdown_content(state, body, empty_recovery=empty_recovery)
        next_hash = digest(body)
        next_file_key = None if deleted or empty_recovery else await write_file(state, body)
    elif file_body is not None:
        next_file_key = await write_file(state, file_body)
        next_content, next_blocks, next_hash = None, None, digest(file_body)
    deleted_condition = (
        Document.deleted_at.is_not(None) if deleted and doc.deleted_at else Document.deleted_at.is_(None)
    )
    result = await db.execute(
        update(Document)
        .where(Document.id == doc.id, Document.revision == expected_revision, deleted_condition)
        .values(
            revision=expected_revision + 1,
            title=title.strip() if title is not None else doc.title,
            filename=filename or doc.filename,
            format=fmt or doc.format,
            source_metadata=next_metadata,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise AppError(40901, "文档已更新，请刷新后重试", 409)
    await db.refresh(doc)
    db.add(
        DocumentRevision(
            document_id=doc.id,
            number=doc.revision,
            filename=doc.filename,
            format=doc.format,
            file_key=next_file_key,
            content_hash=next_hash,
            content=next_content,
            blocks=next_blocks,
            page_count=old.page_count if file_body is None else None,
            source_metadata=next_metadata,
        )
    )
    if empty_recovery and not deleted:
        mark_empty_recovery(doc)
    elif not deleted:
        await add_job(db, doc, kb.options)
    return await document_view(db, doc)


async def delete_document(db, doc):
    cleanup_index_id = doc.desired_index_id or doc.active_index_id
    if cleanup_index_id is None:
        cleanup_index_id = await db.scalar(
            select(IndexRevision.id)
            .where(IndexRevision.document_id == doc.id, IndexRevision.status != "historical")
            .limit(1)
        )
    doc.deleted_at = now()
    doc.status = "deleted"
    doc.active_index_id = None
    await db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.document_id == doc.id, ProcessingJob.status.in_(["pending", "processing"]))
        .values(status="cancelled", stage="cancelled", lease_token=None, lease_until=None)
    )
    # 清理任务持久化；向量和文件删除失败可在重启后继续执行。
    if cleanup_index_id is not None:
        db.add(
            ProcessingJob(
                document_id=doc.id, revision=doc.revision, index_id=cleanup_index_id, stage="cleanup"
            )
        )
    await db.flush()
    return {"id": doc.id}


async def list_documents(
    db,
    kb,
    page_number,
    page_size,
    query=None,
    status=None,
    fmt=None,
    doc_type=None,
    corpus_tier=None,
    law_name=None,
    sort="-created_at",
):
    conditions = [Document.knowledge_base_id == kb.id, Document.deleted_at.is_(None)]
    if query:
        conditions.append(Document.title.contains(query, autoescape=True))
    if status == "indexing":
        conditions.append(Document.status.in_(["parsing", "chunking", "embedding", "pending"]))
    elif status:
        conditions.append(Document.status == status)
    if fmt:
        conditions.append(Document.format == fmt)
    if doc_type is not None:
        conditions.append(Document.source_metadata["doc_type"].as_string() == doc_type)
    if corpus_tier is not None:
        conditions.append(Document.source_metadata["corpus_tier"].as_integer() == corpus_tier)
    if law_name:
        conditions.append(
            Document.source_metadata["law_name"].as_string().contains(law_name, autoescape=True)
        )
    sorting = {
        "created_at": Document.created_at,
        "title": Document.title,
        "effective_date": Document.source_metadata["effective_date"].as_string(),
    }
    column = sorting.get(sort.removeprefix("-"))
    if column is None:
        raise invalid("排序字段不支持")
    total = await db.scalar(select(func.count()).select_from(Document).where(*conditions))
    docs = (
        await db.scalars(
            select(Document)
            .where(*conditions)
            .order_by(column.desc() if sort.startswith("-") else column.asc(), Document.id)
            .offset((page_number - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return page([await document_view(db, doc) for doc in docs], total, page_number, page_size)
