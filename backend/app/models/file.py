"""文件对象模型（内容寻址）。

对应 04-数据库设计 §4.1 与 §5.3。

**内容寻址**：对象存储中的路径为 `files/{sha256前两位}/{sha256}`，以内容哈希
命名而非 UUID。带来两项性质：天然去重、完整性自校验。

⚠️ `uploader_id` 记录"谁最先上传了这个内容"，**不代表文件属于他**。
文件归属由引用它的业务表决定（如 `contract.owner_id`）。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.base import (
    BIGINT_PK,
    DATETIME_MS,
    MYSQL_TABLE_ARGS,
    Base,
    TimestampMixin,
    fk,
)


class FileObject(Base, TimestampMixin):
    __tablename__ = "file_object"
    __table_args__ = (
        UniqueConstraint("sha256", name="uk_file_object_sha256"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    # CHAR(64) 存十六进制小写；DDL 中另有 CHECK (CHAR_LENGTH = 64) 约束兜底，
    # 因为非严格 sql_mode 下列长度不会拒绝过短值（见 04-数据库设计 §2.2）
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    uploader_id: Mapped[int | None] = mapped_column(
        BIGINT_PK, fk("user.id", name="fk_file_object_uploader"), nullable=True, default=None
    )
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)
