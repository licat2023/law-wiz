"""文档、内容修订与导入来源记录。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import BODY, Base, Identity


class Document(Base, Identity):
    """保存当前文档状态。生效索引与等待发布的目标索引分别记录。"""

    __tablename__ = "kb_document"
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("kb_knowledge_base.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(300))
    format: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    active_index_id: Mapped[str | None] = mapped_column(String(36), default=None)
    desired_index_id: Mapped[str | None] = mapped_column(String(36), default=None)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class DocumentRevision(Base, Identity):
    """保存单次修订的原文件引用、正文及块定位信息。"""

    __tablename__ = "kb_document_revision"
    __table_args__ = (UniqueConstraint("document_id", "number"),)
    document_id: Mapped[str] = mapped_column(ForeignKey("kb_document.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(300))
    format: Mapped[str] = mapped_column(String(16))
    file_key: Mapped[str | None] = mapped_column(String(100), default=None)
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str | None] = mapped_column(BODY, default=None)
    blocks: Mapped[list | None] = mapped_column(JSON, default=None)
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    parser_version: Mapped[str] = mapped_column(String(32), default="text-v1")


class ImportRecord(Base, Identity):
    """按库和来源标识关联导入目标，保留最近一次导入结果供重放。"""

    __tablename__ = "kb_import"
    __table_args__ = (UniqueConstraint("knowledge_base_id", "source_namespace", "source_document_id"),)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("kb_knowledge_base.id"))
    source_namespace: Mapped[str] = mapped_column(String(100))
    source_document_id: Mapped[str] = mapped_column(String(100))
    document_id: Mapped[str] = mapped_column(ForeignKey("kb_document.id"))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
