"""问答业务逻辑（M3 的 E 组）。

**服务层不依赖 HTTP**：接收普通参数、抛 `BusinessError`、返回普通对象。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now_beijing, to_iso
from app.core.errors import BusinessError, ErrorCode, Page
from app.models.knowledge import KbChunk, KbDocument
from app.models.qa import QaCitation, QaMessage, QaSession
from app.slices.qa.pipeline import run_answer_pipeline
from app.slices.qa.schemas import (
    AskData,
    CitationItem,
    CreateSessionRequest,
    MessageItem,
    SessionData,
    SessionDetailData,
    SessionListItem,
)

_MAX_PAGE_SIZE = 100

_SORT_OPTIONS = {
    "-last_message_at": QaSession.last_message_at.desc(),
    "last_message_at": QaSession.last_message_at.asc(),
    "-created_at": QaSession.created_at.desc(),
    "created_at": QaSession.created_at.asc(),
}


# ============================================================
# E-01 创建会话
# ============================================================


def create_session(db: Session, *, user_id: int, payload: CreateSessionRequest) -> SessionData:
    session = QaSession(user_id=user_id, title=payload.title, status="active")
    db.add(session)
    db.flush()
    return _to_session_data(session)


def _to_session_data(session: QaSession) -> SessionData:
    return SessionData(
        session_id=str(session.id),
        title=session.title,
        status=session.status,
        message_count=session.message_count,
        created_at=to_iso(session.created_at) or "",
    )


# ============================================================
# E-02 会话列表
# ============================================================


def list_sessions(
    db: Session,
    *,
    user_id: int,
    page: int,
    page_size: int,
    status: str | None,
    sort: str,
) -> tuple[list[SessionListItem], int]:
    if page < 1 or page_size < 1 or page_size > _MAX_PAGE_SIZE:
        raise BusinessError(
            ErrorCode.PAGE_OUT_OF_RANGE, f"分页参数超出范围（page_size 上限 {_MAX_PAGE_SIZE}）"
        )
    order_by = _SORT_OPTIONS.get(sort)
    if order_by is None:
        raise BusinessError(ErrorCode.PARAM_INVALID, "sort 取值不合法")

    conditions = [QaSession.user_id == user_id, QaSession.deleted_at.is_(None)]
    if status is not None:
        conditions.append(QaSession.status == status)

    total = db.scalar(select(func.count()).select_from(QaSession).where(*conditions)) or 0
    sessions = db.scalars(
        select(QaSession)
        .where(*conditions)
        .order_by(order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        SessionListItem(
            session_id=str(session.id),
            title=session.title,
            status=session.status,
            message_count=session.message_count,
            last_message_at=to_iso(session.last_message_at),
            created_at=to_iso(session.created_at) or "",
        )
        for session in sessions
    ]
    return items, int(total)


# ============================================================
# E-03 会话详情（含消息）
# ============================================================


def get_session(
    db: Session, *, user_id: int, session_id: int, page: int, page_size: int
) -> SessionDetailData:
    session = _load_owned_session(db, user_id=user_id, session_id=session_id)
    if page < 1 or page_size < 1 or page_size > _MAX_PAGE_SIZE:
        raise BusinessError(
            ErrorCode.PAGE_OUT_OF_RANGE, f"分页参数超出范围（page_size 上限 {_MAX_PAGE_SIZE}）"
        )

    total = (
        db.scalar(select(func.count()).select_from(QaMessage).where(QaMessage.qa_session_id == session.id))
        or 0
    )
    messages = db.scalars(
        select(QaMessage)
        .where(QaMessage.qa_session_id == session.id)
        .order_by(QaMessage.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    citations = _load_citations(db, [message.id for message in messages])
    items = [_to_message_item(message, citations.get(message.id, [])) for message in messages]

    return SessionDetailData(
        session_id=str(session.id),
        title=session.title,
        status=session.status,
        messages=Page.of(items, page, page_size, int(total)),
    )


def _load_citations(db: Session, message_ids: list[int]) -> dict[int, list[CitationItem]]:
    """取消息的引用，并回表补上 `law_name` / `article_no`。

    引用条数很少（每答最多几条），这次回表换取的"可读引用"是必要的 ——
    用户点击"依据"时看到的正是这些字段（05-接口设计 §5.6）。
    """
    if not message_ids:
        return {}

    citations = db.scalars(select(QaCitation).where(QaCitation.qa_message_id.in_(message_ids))).all()
    if not citations:
        return {}

    chunk_ids = {c.kb_chunk_id for c in citations if c.kb_chunk_id}
    document_ids = {c.kb_document_id for c in citations if c.kb_document_id}
    chunks = (
        {chunk.id: chunk for chunk in db.scalars(select(KbChunk).where(KbChunk.id.in_(chunk_ids))).all()}
        if chunk_ids
        else {}
    )
    documents = (
        {
            document.id: document
            for document in db.scalars(select(KbDocument).where(KbDocument.id.in_(document_ids))).all()
        }
        if document_ids
        else {}
    )

    grouped: dict[int, list[CitationItem]] = {}
    for citation in citations:
        chunk = chunks.get(citation.kb_chunk_id) if citation.kb_chunk_id else None
        document = documents.get(citation.kb_document_id) if citation.kb_document_id else None
        grouped.setdefault(citation.qa_message_id, []).append(
            CitationItem(
                document_id=str(citation.kb_document_id) if citation.kb_document_id else None,
                kb_chunk_id=str(citation.kb_chunk_id) if citation.kb_chunk_id else None,
                law_name=(chunk.law_name if chunk else None) or (document.law_name if document else None),
                article_no=(chunk.article_no if chunk else None)
                or (document.article_no if document else None),
                quoted_text=citation.quoted_text,
                relevance_score=float(citation.relevance_score)
                if citation.relevance_score is not None
                else None,
            )
        )
    return grouped


def _to_message_item(message: QaMessage, citations: list[CitationItem]) -> MessageItem:
    return MessageItem(
        message_id=str(message.id),
        role=message.role,
        content=message.content,
        has_citation=message.has_citation,
        citations=citations,
        model_name=message.model_name,
        latency_ms=message.latency_ms,
        created_at=to_iso(message.created_at) or "",
    )


def _load_owned_session(db: Session, *, user_id: int, session_id: int) -> QaSession:
    session = db.get(QaSession, session_id)
    if session is None or session.deleted_at is not None:
        raise BusinessError(ErrorCode.QA_SESSION_NOT_FOUND, "问答会话不存在")
    if session.user_id != user_id:
        raise BusinessError(ErrorCode.FORBIDDEN, "无权访问该会话")
    return session


# ============================================================
# E-04 提问（异步）
# ============================================================


def ask(db: Session, *, user_id: int, session_id: int, content: str) -> AskData:
    """写入提问与**预分配**的 assistant 消息，返回两者的 ID。

    回答内容由后台流水线填充；前端拿到 `assistant_message_id` 后可先占位
    （"正在思考…"），再按 ID 原地替换（05-接口设计 §5.6）。
    """
    session = _load_owned_session(db, user_id=user_id, session_id=session_id)
    if session.status != "active":
        raise BusinessError(ErrorCode.SESSION_ARCHIVED, "会话已归档，无法继续提问")

    question = QaMessage(qa_session_id=session.id, role="user", content=content)
    db.add(question)
    db.flush()

    answer = QaMessage(qa_session_id=session.id, role="assistant", content="", has_citation=False)
    db.add(answer)
    db.flush()

    if not session.title:
        # 缺省标题由首条提问生成（05-接口设计 §5.6）
        session.title = content[:50]

    session.message_count += 2
    session.last_message_at = now_beijing()
    db.flush()

    return AskData(
        user_message_id=str(question.id),
        assistant_message_id=str(answer.id),
        status="pending",
    )


def enqueue(*, message_id: int, session_id: int) -> None:
    """登记并执行回答生成。

    单独成函数是为了**让测试可以替换它** —— 测试里不应真的调用模型。
    """
    run_answer_pipeline(message_id=message_id, session_id=session_id)


# ============================================================
# E-05 归档会话
# ============================================================


def archive(db: Session, *, user_id: int, session_id: int) -> None:
    """**归档而非物理删除**：`status` 置为 `archived`，历史问答保留可查。"""
    session = _load_owned_session(db, user_id=user_id, session_id=session_id)
    session.status = "archived"
    db.flush()
