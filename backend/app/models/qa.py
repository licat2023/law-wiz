"""法律问答模型（M3，P1）。

对应 04-数据库设计 §5.13 ~ §5.15。

两条关键设计：
1. `qa_message` **只增不改**（无 `updated_at`、无软删除）。
2. `qa_citation` 是"回答溯源"功能（M3-04）的**全部数据基础** ——
   用户点击"依据"时，界面展示的正是本表关联的 `quoted_text` 与法条信息。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now_beijing
from app.infra.db.base import (
    BIGINT_PK,
    DATETIME_MS,
    MEDIUMTEXT_V,
    MYSQL_TABLE_ARGS,
    SERVER_NOW_MS,
    Base,
    TimestampMixin,
    fk,
)


class QaSession(Base, TimestampMixin):
    """一次多轮对话。"""

    __tablename__ = "qa_session"
    __table_args__ = (
        # 会话列表按最近消息时间排序（04-数据库设计 §5.13）
        Index("idx_qa_session_user", "user_id", "last_message_at"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT_PK, fk("user.id", name="fk_qa_session_user"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    # 冗余统计，避免会话列表页反复聚合
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_message_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)

    messages: Mapped[list[QaMessage]] = relationship(back_populates="session", cascade="all, delete-orphan")


class QaMessage(Base):
    """会话中的单条消息（**只增不改**）。

    `model_name` 与 `latency_ms` **不是冗余**：需求要求"LLM 服务支持替换"，
    替换后必须能对比不同模型的表现；需求也规定了问答响应时间（≤5 秒），
    不记录耗时就无法证明达标。
    """

    __tablename__ = "qa_message"
    __table_args__ = (
        # 会话详情按会话取消息并稳定分页（04-数据库设计 §5.14）
        Index("idx_qa_message_session", "qa_session_id", "id"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    qa_session_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("qa_session.id", name="fk_qa_message_session"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(MEDIUMTEXT_V, nullable=False)
    # ⚠️ 无依据时**必须为 False 且内容中标注"未找到直接法律依据"**。
    # 这是"回答溯源"的反面 —— 溯源不了的时候要说出来（05-接口设计 §5.6）
    has_citation: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(
        DATETIME_MS, nullable=False, default=now_beijing, server_default=SERVER_NOW_MS
    )

    session: Mapped[QaSession] = relationship(back_populates="messages")
    citations: Mapped[list[QaCitation]] = relationship(back_populates="message", cascade="all, delete-orphan")


class QaCitation(Base):
    """回答引用的知识库文档与法条。**"回答溯源"的全部数据基础。**"""

    __tablename__ = "qa_citation"
    __table_args__ = (MYSQL_TABLE_ARGS,)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    qa_message_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("qa_message.id", name="fk_qa_citation_message"), nullable=False
    )
    kb_document_id: Mapped[int | None] = mapped_column(
        BIGINT_PK, fk("kb_document.id", name="fk_qa_citation_doc"), nullable=True, default=None
    )
    kb_chunk_id: Mapped[int | None] = mapped_column(
        BIGINT_PK, fk("kb_chunk.id", name="fk_qa_citation_chunk"), nullable=True, default=None
    )
    quoted_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    relevance_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(
        DATETIME_MS, nullable=False, default=now_beijing, server_default=SERVER_NOW_MS
    )

    message: Mapped[QaMessage] = relationship(back_populates="citations")
