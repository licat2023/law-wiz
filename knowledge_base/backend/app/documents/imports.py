"""从旧语料导入正文、历史块和引用映射。"""

from sqlalchemy import select

from app.documents.models import Document, ImportRecord
from app.documents.service import change_document, create_document, delete_document
from app.errors import AppError
from app.indexing.models import Chunk, IndexRevision
from app.infrastructure.database import new_id
from app.infrastructure.idempotency import digest


async def import_document(db, state, kb, payload):
    hashed = digest(payload.model_dump())
    record = await db.scalar(
        select(ImportRecord).where(
            ImportRecord.knowledge_base_id == kb.id,
            ImportRecord.source_namespace == payload.source_namespace,
            ImportRecord.source_document_id == payload.source_document_id,
        )
    )
    if record and record.payload_hash == hashed:
        return record.result
    metadata = payload.metadata | {
        "source_namespace": payload.source_namespace,
        "source_document_id": payload.source_document_id,
    }
    deleted = bool(metadata.get("deleted_at"))
    empty_recovery = not payload.content.strip()
    if record:
        doc = await db.get(Document, record.document_id)
        was_deleted = doc.deleted_at is not None
        if was_deleted and not deleted:
            raise AppError(40903, "目标文档已删除，导入不能将其自动恢复", 409)
        await change_document(
            db,
            state,
            kb,
            doc,
            doc.revision,
            title=payload.title,
            content=payload.content,
            metadata=metadata,
            deleted=deleted,
            empty_recovery=empty_recovery,
        )
        if deleted and not was_deleted:
            await delete_document(db, doc)
    else:
        result = await create_document(
            db,
            state,
            kb,
            payload.title,
            "restored.md",
            "markdown",
            payload.content.encode(),
            metadata,
            content=payload.content,
            deleted=deleted,
            empty_recovery=empty_recovery,
        )
        doc = await db.get(Document, result["id"])
        record = ImportRecord(
            knowledge_base_id=kb.id,
            source_namespace=payload.source_namespace,
            source_document_id=payload.source_document_id,
            document_id=doc.id,
            payload_hash=hashed,
            result={},
        )
        db.add(record)
    history = IndexRevision(
        document_id=doc.id,
        revision=doc.revision,
        options={"source": "migration_history"},
        status="historical",
    )
    db.add(history)
    await db.flush()
    mapping = {}
    for number, value in enumerate(payload.history_chunks):
        chunk_id = new_id()
        source_id = value.get("id", value.get("chunk_id"))
        if source_id is not None:
            mapping[str(source_id)] = chunk_id
        body = str(value.get("content", ""))
        db.add(
            Chunk(
                id=chunk_id,
                index_id=history.id,
                parent_id=None,
                level=0,
                chunk_no=int(value.get("chunk_no", number)),
                content=body,
                char_start=int(value.get("char_start", 0)),
                char_end=int(value.get("char_end", len(body))),
                article_no=value.get("article_no"),
                title_path=str(value.get("chapter_path") or ""),
            )
        )
    record.payload_hash = hashed
    record.result = {
        "document_id": doc.id,
        "revision": doc.revision,
        "index_id": history.id,
        "chunk_ids": mapping,
    }
    await db.flush()
    return record.result
