"""知识库与其默认索引设置。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base, Identity


class KnowledgeBase(Base, Identity):
    __tablename__ = "kb_knowledge_base"
    application_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[dict] = mapped_column(JSON)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
