"""索引修订、检索块与处理任务。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import BODY, Base, Identity


class IndexRevision(Base, Identity):
    """记录某次索引对应的文档修订、切分配置及发布时使用的向量空间。"""

    __tablename__ = "kb_index_revision"
    document_id: Mapped[str] = mapped_column(ForeignKey("kb_document.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    options: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)


class Chunk(Base, Identity):
    """保存用于召回或上下文补全的文本块。仅叶块写入向量库。"""

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


class KeywordLeaf(Base):
    """BM25 的叶块长度，与同一批次的 Chroma ID 共用主键。"""

    __tablename__ = "kb_keyword_leaf"
    chunk_id: Mapped[str] = mapped_column(ForeignKey("kb_chunk.id"), primary_key=True)
    index_id: Mapped[str] = mapped_column(ForeignKey("kb_index_revision.id"), index=True)
    length: Mapped[int] = mapped_column(Integer)


class KeywordPosting(Base):
    """保存归一化词项在单个叶块中的频次。摘要使匹配独立于数据库排序规则。"""

    __tablename__ = "kb_keyword_posting"
    term: Mapped[str] = mapped_column(String(32), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("kb_keyword_leaf.chunk_id"), primary_key=True, index=True
    )
    frequency: Mapped[int] = mapped_column(Integer)


class ProcessingJob(Base, Identity):
    """记录索引或清理工作的执行阶段、认领次数和可过期的租约。"""

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
