"""问答生成流水线（异步）。

⚠️ 约定与其它流水线相同：**同步函数**、由 `BackgroundTasks` 放进线程池、
只调用 `app/infra/*` 的封装，不实现任何 AI 能力。

⚠️ **`qa_message` 没有状态列与错误列**（见 04-数据库设计 §5.14，消息表只增不改）。
因此生成失败时**无法记录"失败状态"**，只能把说明写进 `content` ——
前端看到的就是这条内容。`has_citation` 同时置为 `false`，
使"这条回答没有依据"在界面上是显式的。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_beijing
from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode
from app.infra import llm, vector
from app.infra.db.session import SessionLocal
from app.models.knowledge import KbChunk, KbDocument
from app.models.qa import QaCitation, QaMessage, QaSession
from app.slices.qa import prompts

logger = logging.getLogger("lawwiz.qa")

_settings = get_settings()

_GENERATION_FAILED = "回答生成失败，请稍后重试。"


def run_answer_pipeline(*, message_id: int, session_id: int) -> None:
    """生成 assistant 消息的内容与引用。**异常一律写进消息内容**，不向外抛。"""
    db = SessionLocal()
    try:
        message = db.get(QaMessage, message_id)
        session = db.get(QaSession, session_id)
        if message is None or session is None:
            logger.warning("消息 %s 或会话 %s 不存在，跳过生成", message_id, session_id)
            return

        question = _load_question(db, session_id=session_id, before_message_id=message_id)
        if question is None:
            _write_failure(db, message, "未找到对应的提问，无法生成回答。")
            return

        started = time.perf_counter()
        context, candidates = _build_context(db, question)
        result = llm.complete_structured(
            prompts.QA_SYSTEM,
            prompts.QA_USER_TEMPLATE.format(context=context, question=question),
            prompts.QA_SCHEMA,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        answer = str(result.get("answer") or "").strip()
        if not answer:
            raise BusinessError(ErrorCode.LLM_BAD_RESPONSE, "模型未返回回答内容")

        citations = _record_citations(
            db, message=message, used=result.get("used_indexes"), candidates=candidates
        )
        message.content = answer
        message.has_citation = bool(citations)
        message.model_name = _settings.llm_model
        message.latency_ms = elapsed_ms
        db.commit()
        logger.info("消息 %s 生成完成，引用 %d 条，耗时 %dms", message_id, len(citations), elapsed_ms)

    except BusinessError as exc:
        _write_failure(db, message_id, str(exc.message))
    except Exception:
        logger.exception("消息 %s 生成失败", message_id)
        _write_failure(db, message_id, _GENERATION_FAILED)
    finally:
        db.close()


def _load_question(db: Session, *, session_id: int, before_message_id: int) -> str | None:
    """取该 assistant 消息之前最近的一条 user 消息作为提问。"""
    return db.scalar(
        select(QaMessage.content)
        .where(
            QaMessage.qa_session_id == session_id,
            QaMessage.role == "user",
            QaMessage.id < before_message_id,
        )
        .order_by(QaMessage.id.desc())
        .limit(1)
    )


def _build_context(db: Session, question: str) -> tuple[str, list[dict]]:
    """检索法条片段并拼成上下文。

    返回 (上下文文本, 候选列表)。候选列表的 `index` 与提示词里片段序号一一对应，
    模型回报的 `used_indexes` 据此映射回具体分块。
    """
    hits = vector.search(question, top_k=prompts.MAX_CONTEXT_CHUNKS)
    if not hits:
        return "（未检索到相关法条）", []

    chunk_ids = [int(hit.chunk_id) for hit in hits if hit.chunk_id.isdigit()]
    chunks = {chunk.id: chunk for chunk in db.scalars(select(KbChunk).where(KbChunk.id.in_(chunk_ids))).all()}
    document_ids = {chunk.kb_document_id for chunk in chunks.values()}
    documents = {
        document.id: document
        for document in db.scalars(select(KbDocument).where(KbDocument.id.in_(document_ids))).all()
    }

    candidates: list[dict] = []
    lines: list[str] = []
    for hit in hits:
        if not hit.chunk_id.isdigit():
            continue
        chunk = chunks.get(int(hit.chunk_id))
        if chunk is None:
            continue
        document = documents.get(chunk.kb_document_id)
        if document is None or document.deleted_at is not None:
            continue
        # 已废止法条**不得进入上下文**：据以作答是本项目最严重的失败形态之一
        if document.abolished_date is not None:
            continue

        index = len(candidates) + 1
        label = f"{chunk.law_name or document.law_name or document.title}"
        if chunk.article_no or document.article_no:
            label += f" {chunk.article_no or document.article_no}"
        candidates.append(
            {
                "index": index,
                "chunk": chunk,
                "document": document,
                "quoted_text": chunk.content,
                "score": hit.score,
            }
        )
        lines.append(f"[{index}] {label}\n{chunk.content}")

    return ("\n\n".join(lines) if lines else "（未检索到相关法条）"), candidates


def _record_citations(
    db: Session, *, message: QaMessage, used: object, candidates: list[dict]
) -> list[QaCitation]:
    """按模型回报的片段序号建立引用记录。

    ⚠️ **只记录模型实际依据的片段**，而不是"检索到的全部片段" ——
    后者会让引用看起来比实际更充分，违背"回答溯源"的目的。
    """
    indexes: set[int] = set()
    if isinstance(used, list):
        for item in used:
            if isinstance(item, int):
                indexes.add(item)
            elif isinstance(item, str) and item.isdigit():
                indexes.add(int(item))

    citations: list[QaCitation] = []
    for candidate in candidates:
        if candidate["index"] not in indexes:
            continue
        chunk: KbChunk = candidate["chunk"]
        document: KbDocument = candidate["document"]
        citation = QaCitation(
            qa_message_id=message.id,
            kb_document_id=document.id,
            kb_chunk_id=chunk.id,
            quoted_text=candidate["quoted_text"],
            relevance_score=candidate["score"],
        )
        db.add(citation)
        citations.append(citation)

    if indexes and not citations:
        # 模型回报了序号，但都对不上候选（例如编造了序号）—— 如实降级为"无依据"
        logger.warning("模型回报的 used_indexes %s 与候选片段对不上", sorted(indexes))
    return citations


def _write_failure(db: Session, message: QaMessage | int, reason: str) -> None:
    """把失败写进消息内容。**`qa_message` 没有状态列，这是唯一的记录方式。**"""
    try:
        db.rollback()
        target = db.get(QaMessage, message) if isinstance(message, int) else message
        if target is None:
            return
        target.content = _GENERATION_FAILED if reason == _GENERATION_FAILED else f"回答生成失败：{reason}"
        target.has_citation = False
        target.created_at = target.created_at or now_beijing()
        db.commit()
    except Exception:
        logger.exception("写入回答失败状态时又出错了")
