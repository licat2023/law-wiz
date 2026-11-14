"""索引修订、检索块与处理任务。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import BODY, Base, Identity


class IndexRevision(Base, Identity):
    __tablename__ = "kb_index_revision"
    document_id: Mapped[str] = mapped_column(ForeignKey("kb_document.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    options: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)


class Chunk(Base, Identity):
    __tablename__ = "kb_chunk"
    __table_args__ = (Index("ix_kb_chunk_version_order", "index_id", "chunk_no"),)
    index_id: Mapped[str] = mapped_column(ForeignKey("kb_index_revision.id"))
    parent_id: Mapped[str | None] = mapped_column(String(36), default=None)
    level: Mapped[int] = mapped_column(Integer)
    chunk_no: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(BODY)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    title_path: Mapped[str] = mapped_column(String(2000), default="")
    page_number: Mapped[int | None] = mapped_column(Integer, default=None)
    article_no: Mapped[str | None] = mapped_column(String(64), default=None)
    is_leaf: Mapped[bool] = mapped_column(default=True)


class ProcessingJob(Base, Identity):
    __tablename__ = "kb_processing_job"
    __table_args__ = (Index("ix_kb_job_claim", "status", "lease_until"),)
    document_id: Mapped[str] = mapped_column(ForeignKey("kb_document.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    index_id: Mapped[str] = mapped_column(ForeignKey("kb_index_revision.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    stage: Mapped[str] = mapped_column(String(32), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), default=None)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
