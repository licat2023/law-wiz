"""在生效索引中召回叶块，并用索引对应的文档修订组织引用与法条上下文。"""

import asyncio
import logging
from dataclasses import dataclass

from chromadb.errors import ChromaError
from sqlalchemy import case, select
from sqlalchemy.exc import SQLAlchemyError

from app.documents.models import Document
from app.documents.service import revision_of
from app.errors import AppError, invalid
from app.indexing.keyword import keyword_search
from app.indexing.models import Chunk, IndexRevision
from app.infrastructure.database import now

logger = logging.getLogger("knowledge_base.retrieval")


@dataclass
class Recall:
    """隔离单路失败，并保存可在测试界面核对的候选次序。"""

    status: str
    hits: list[tuple[str, float]]
    error: AppError | None = None
    versions: int | None = None

    def diagnostic(self):
        return {
            "status": self.status,
            "indexed_versions": self.versions,
            "candidates": [{"chunk_id": chunk_id, "score": score} for chunk_id, score in self.hits],
        }


async def _vector_recall(state, kb_id, eligible, query, limit, *, allow_partial):
    indexes = [
        key for key, (_, index, _) in eligible.items() if index.fingerprint == state.embedding.fingerprint
    ]
    mismatch = len(eligible) != len(indexes)
    if mismatch and (not indexes or not allow_partial):
        error = AppError(40904, "嵌入模型配置已变更，请重建知识库文档索引", 409)
        return Recall("fingerprint_changed", [], error, len(indexes))
    try:
        embedding = (await state.embedding.embed([query]))[0]
        hits = await asyncio.to_thread(
            state.vector.query, state.embedding.fingerprint, kb_id, indexes, embedding, limit
        )
        return Recall("partial" if mismatch else "ok", hits, versions=len(indexes))
    except (AppError, ChromaError, OSError, ValueError, TimeoutError) as exc:
        logger.warning("向量召回失败 (%s)", type(exc).__name__)
        error = exc if isinstance(exc, AppError) else AppError(50201, "向量检索暂不可用", 502)
        return Recall("unavailable", [], error, len(indexes))


async def _keyword_recall(state, eligible, query, limit):
    try:
        # 独立读会话隔离关键词连接中断，保留主会话用于回查向量命中。
        async with state.sessions() as keyword_db:
            hits, versions = await keyword_search(keyword_db, list(eligible), query, limit)
        return Recall(
            "legacy" if not versions else "partial" if versions < len(eligible) else "ok",
            hits,
            versions=versions,
        )
    except SQLAlchemyError as exc:
        logger.warning("关键词召回失败 (%s)", type(exc).__name__)
        return Recall("unavailable", [], AppError(50201, "关键词检索暂不可用", 502))


def _fuse(vector, keyword):
    vector_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(vector, 1)}
    keyword_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(keyword, 1)}
    if vector and keyword:
        # RRF 只使用路内排名。归一化使对外相关度维持在 [0, 1]。
        hits = [
            (
                chunk_id,
                61
                / 2
                * sum(
                    1 / (60 + ranks[chunk_id]) for ranks in (vector_ranks, keyword_ranks) if chunk_id in ranks
                ),
            )
            for chunk_id in vector_ranks.keys() | keyword_ranks.keys()
        ]
        hits.sort(key=lambda hit: (-hit[1], vector_ranks.get(hit[0], len(vector) + 1), hit[0]))
    else:
        hits = vector or [(chunk_id, float(score) / (1 + float(score))) for chunk_id, score in keyword]
    return hits, vector_ranks, keyword_ranks


async def _rerank(state, query, ranked, chunks, eligible):
    if not state.reranker:
        return ranked, "disabled", []
    candidates = ranked[: state.settings.rerank_candidates]
    if not candidates:
        return ranked, "no_candidates", []
    texts = []
    for chunk_id, _ in candidates:
        chunk = chunks[chunk_id]
        doc, _, metadata = eligible[chunk.index_id]
        law = metadata.get("law_name") or doc.title
        texts.append(f"{law}\n{chunk.article_no or ''}\n{chunk.content}")
    try:
        scores = await state.reranker.rank(query, texts)
    except AppError:
        logger.warning("重排服务不可用，使用融合顺序")
        return ranked, "fallback", []
    ordered = sorted(
        ((hit[0], score) for hit, score in zip(candidates, scores, strict=True)), key=lambda hit: -hit[1]
    )
    return ordered + ranked[len(candidates) :], "ok", ordered


def _diagnostics(strategy, vector, keyword, fused, rerank_status, reranked):
    def candidates(hits):
        return [{"chunk_id": chunk_id, "score": score} for chunk_id, score in hits]

    return {
        "strategy": strategy,
        "vector": vector.diagnostic(),
        "keyword": keyword.diagnostic(),
        "fused": candidates(fused),
        "rerank": {"status": rerank_status, "candidates": candidates(reranked)},
    }


async def search(db, state, kb, payload):
    """召回共同授权范围内的生效叶块，返回去重法条及受限的正文上下文。"""
    if not payload.query.strip():
        raise invalid("检索问题不能为空")
    strategy = payload.strategy or state.settings.retrieval_strategy
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
    today = now().date().isoformat()
    for doc, index in pairs:
        # 用索引对应的修订过滤。文档编辑后的元数据要等新索引发布才用于检索。
        revision = await revision_of(db, doc.id, index.revision)
        metadata = revision.source_metadata
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
        eligible[index.id] = (doc, index, metadata)
    if not eligible:
        data = {"query": payload.query, "items": [], "article_contents": {}, "article_limit_reached": False}
        if payload.diagnostics:
            empty = Recall("no_candidates", [], versions=0)
            data["diagnostics"] = _diagnostics(strategy, empty, empty, [], "no_candidates", [])
        return data
    # 候选召回期间释放主会话连接，避免并发检索占满连接池。
    await db.commit()
    limit = payload.top_k if strategy == "vector" else max(payload.top_k, state.settings.retrieval_candidates)
    vector_call = _vector_recall(
        state, kb.id, eligible, payload.query, limit, allow_partial=strategy != "vector"
    )
    if strategy == "vector":
        vector, keyword = await vector_call, Recall("skipped", [])
    else:
        vector, keyword = await asyncio.gather(
            vector_call, _keyword_recall(state, eligible, payload.query, limit)
        )
    if vector.error and (keyword.error or not keyword.versions):
        raise vector.error
    fused, vector_ranks, keyword_ranks = _fuse(vector.hits, keyword.hits)
    chunks = {
        c.id: c
        for c in (
            await db.scalars(
                select(Chunk).where(
                    Chunk.id.in_([h[0] for h in fused]),
                    Chunk.index_id.in_(eligible),
                    Chunk.is_leaf.is_(True),
                )
            )
        ).all()
    }
    fused = [hit for hit in fused if hit[0] in chunks]
    article_budget = min(state.settings.max_text_chars, 16000)
    parent_cap = max(article_budget, state.settings.parent_context_chars)
    parents = {
        c.id: c
        for c in (
            await db.execute(
                select(
                    Chunk.id,
                    Chunk.index_id,
                    Chunk.article_no,
                    case(
                        (Chunk.char_end - Chunk.char_start <= parent_cap, Chunk.content),
                        else_=None,
                    ).label("content"),
                ).where(
                    Chunk.id.in_([c.parent_id for c in chunks.values() if c.parent_id]),
                    Chunk.index_id.in_(eligible),
                )
            )
        ).all()
    }
    # 释放主会话连接后调用远程重排，再检查查询期间是否删除或切换索引。
    await db.commit()
    ranked, rerank_status, reranked = (
        await _rerank(state, payload.query, fused, chunks, eligible)
        if strategy == "reranked"
        else (fused, "skipped", [])
    )
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
    article_limit_reached = False
    rerank_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(reranked, 1)}
    fused_ranks = {chunk_id: rank for rank, (chunk_id, _) in enumerate(fused, 1)}
    for chunk_id, score in ranked:
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
            if article_id in article_contents:
                continue
            if parent.content is None or len(parent.content) > article_budget:
                article_limit_reached = True
                continue
            article_contents[article_id] = parent.content
            article_budget -= len(parent.content)
        parent_text = None
        if parent and parent.content and parent.id not in seen_parents and len(parent.content) <= budget:
            parent_text = parent.content
            budget -= len(parent_text)
            seen_parents.add(parent.id)
        item = {
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
        if payload.diagnostics:
            item["retrieval_sources"] = [
                source
                for source, ranks in (("vector", vector_ranks), ("keyword", keyword_ranks))
                if chunk_id in ranks
            ]
            item["ranks"] = {
                "vector": vector_ranks.get(chunk_id),
                "keyword": keyword_ranks.get(chunk_id),
                "fused": fused_ranks[chunk_id],
                "rerank": rerank_ranks.get(chunk_id),
            }
        items.append(item)
        if len(items) >= payload.top_k:
            break
    data = {
        "query": payload.query,
        "items": items,
        "article_contents": article_contents,
        "article_limit_reached": article_limit_reached,
    }
    if payload.diagnostics:
        # 诊断候选同样遵守返回前的生效版本复核。
        live_chunks = {
            chunk.id
            for chunk in chunks.values()
            if live.get(eligible[chunk.index_id][0].id) == chunk.index_id
        }
        for recall in (vector, keyword):
            recall.hits = [hit for hit in recall.hits if hit[0] in live_chunks]
        data["diagnostics"] = _diagnostics(
            strategy,
            vector,
            keyword,
            [hit for hit in fused if hit[0] in live_chunks],
            rerank_status,
            [hit for hit in reranked if hit[0] in live_chunks],
        )
    return data
