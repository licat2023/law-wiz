"""记录写入请求的幂等键与结果。"""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class IdempotencyRecord(Base):
    """用调用方、操作范围和幂等键的摘要定位已保存的请求结果。"""

    __tablename__ = "kb_idempotency"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
