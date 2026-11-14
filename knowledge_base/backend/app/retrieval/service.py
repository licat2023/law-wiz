"""在生效索引中召回叶块，并用索引对应的文档修订组织引用与法条上下文。"""

import asyncio

from sqlalchemy import select

from app.documents.models import Document
from app.documents.service import revision_of
from app.errors import AppError, invalid
from app.indexing.models import Chunk, IndexRevision
from app.infrastructure.database import now


async def search(db, state, kb, payload):
    """应用修订元数据和嵌入空间约束，返回仍生效的引用及受限的上下文。"""
    if not payload.query.strip():
        raise invalid("检索问题不能为空")
    pairs = (
        await db.execute(
            select(Document, IndexRevision)
            .join(
                IndexRevision,
                Document.active_index_id == IndexRevision.id,
            )
            .where(
                Document.knowledge_base_id == kb.id,
                Document.deleted_at.is_(None),
                IndexRevision.status == "ready",
            )
        )
    ).all()
    eligible = {}
    for doc, index in pairs:
        # 用索引对应的修订过滤。文档编辑后的元数据要等新索引发布才用于检索。
        revision = await revision_of(db, doc.id, index.revision)
        metadata = revision.source_metadata
        today = now().date().isoformat()
        if (
            not payload.include_abolished
            and metadata.get("abolished_date")
            and metadata["abolished_date"] <= today
        ):
            continue
        if metadata.get("effective_date") and metadata["effective_date"] > today:
            continue
        if payload.doc_type is not None and metadata.get("doc_type") != payload.doc_type:
            continue
        if payload.corpus_tier is not None and metadata.get("corpus_tier") != payload.corpus_tier:
            continue
        if index.fingerprint != state.embedding.fingerprint:
            raise AppError(40904, "嵌入模型配置已变更，请重建知识库文档索引", 409)
        eligible[index.id] = (doc, index, metadata)
    if not eligible:
        return {"query": payload.query, "items": [], "article_contents": {}, "article_limit_reached": False}
    embedding = (await state.embedding.embed([payload.query]))[0]
    hits = await asyncio.to_thread(
        state.vector.query, state.embedding.fingerprint, kb.id, list(eligible), embedding, payload.top_k
    )
    chunks = {
        c.id: c
        for c in (
            await db.scalars(
                select(Chunk).where(
                    Chunk.id.in_([h[0] for h in hits]),
                    Chunk.index_id.in_(eligible),
                    Chunk.is_leaf.is_(True),
                )
            )
        ).all()
    }
    parents = {
        c.id: c
        for c in (
            await db.scalars(
                select(Chunk).where(
                    Chunk.id.in_([c.parent_id for c in chunks.values() if c.parent_id]),
                    Chunk.index_id.in_(eligible),
                )
            )
        ).all()
    }
    # 结束本轮读取事务再检查生效指针，过滤查询期间已删除或切换索引的文档。
    await db.commit()
    live = dict(
        (
            await db.execute(
                select(Document.id, Document.active_index_id)
                .where(
                    Document.id.in_([doc.id for doc, _, _ in eligible.values()]),
                    Document.deleted_at.is_(None),
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    items, seen_parents, budget = [], set(), state.settings.parent_context_chars
    article_contents = {}
    # 完整法条与普通父块分别计量，法条正文按父块 ID 去重。
    article_budget = min(state.settings.max_text_chars, 16000)
    article_limit_reached = False
    for chunk_id, score in hits:
        chunk = chunks.get(chunk_id)
        if chunk is None or chunk.index_id not in eligible:
            continue
        doc, index, metadata = eligible[chunk.index_id]
        if live.get(doc.id) != index.id:
            continue
        parent = parents.get(chunk.parent_id)
        if parent and parent.index_id != index.id:
            parent = None
        article_id = None
        if parent and parent.article_no:
            article_id = parent.id
            if article_id not in article_contents:
                if len(parent.content) > article_budget:
                    article_limit_reached = True
                    continue
                article_contents[article_id] = parent.content
                article_budget -= len(parent.content)
        parent_text = None
        if parent and parent.id not in seen_parents and len(parent.content) <= budget:
            parent_text = parent.content
            budget -= len(parent_text)
            seen_parents.add(parent.id)
        items.append(
            {
                "knowledge_base_id": kb.id,
                "document_id": doc.id,
                "revision": index.revision,
                "index_revision_id": index.id,
                "chunk_id": chunk.id,
                "title": doc.title,
                "content": chunk.content,
                "score": score,
                "parent_content": parent_text,
                "article_chunk_id": article_id,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "page_number": chunk.page_number,
                "metadata": metadata | {"article_no": chunk.article_no or metadata.get("article_no")},
            }
        )
    return {
        "query": payload.query,
        "items": items,
        "article_contents": article_contents,
        "article_limit_reached": article_limit_reached,
    }
