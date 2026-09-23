"""合同与版本模型。

对应 04-数据库设计 §5.4 / §5.5。

⚠️ **合同的文件与文本不在本表**，而在 `contract_version`。这样"上传 → 修改 → 重审"
每次都产生一个不可变版本，审查任务指向具体版本，**不会出现"审查报告对应的是哪一版
文本"说不清的情况**。

`contract.current_version_id` 与 `contract_version.contract_id` **互相引用**（循环外键），
因此该约束由迁移脚本在建表后单独 `ALTER TABLE` 添加。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now_beijing
from app.infra.db.base import (
    BIGINT_PK,
    DATETIME_MS,
    LONGTEXT_V,
    MYSQL_TABLE_ARGS,
    SERVER_NOW_MS,
    Base,
    TimestampMixin,
    fk,
)


class Contract(Base, TimestampMixin):
    """合同。生命周期状态：draft → pending_sign → signing → signed → archived。

    一期只用到 `draft`（上传态）；其余状态属 P3（M6 电子合同签署）。
    """

    __tablename__ = "contract"
    __table_args__ = (MYSQL_TABLE_ARGS,)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BIGINT_PK, fk("user.id", name="fk_contract_owner"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_type: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="upload", server_default="upload")
    # 循环外键：由迁移脚本建表后单独 ALTER 添加
    current_version_id: Mapped[int | None] = mapped_column(BIGINT_PK, nullable=True, default=None)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)


class ContractVersion(Base):
    """合同版本（**只增不改**）。

    ⚠️ `text_source` 记录文本是怎么来的（`parse` 直接解析 / `ocr` 识别）：
    两者的可信度不同，审查报告需要知道"这段文字是识别来的"，以便在结论存疑时
    提示用户核对原件。这是可溯源性的一部分。
    """

    __tablename__ = "contract_version"
    __table_args__ = (
        UniqueConstraint("contract_id", "version_no", name="uk_contract_version"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("contract.id", name="fk_contract_version_contract"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_object_id: Mapped[int | None] = mapped_column(
        BIGINT_PK, fk("file_object.id", name="fk_contract_version_file"), nullable=True, default=None
    )
    plain_text: Mapped[str | None] = mapped_column(LONGTEXT_V, nullable=True, default=None)
    text_source: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_by: Mapped[int] = mapped_column(
        BIGINT_PK, fk("user.id", name="fk_contract_version_creator"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DATETIME_MS, nullable=False, default=now_beijing, server_default=SERVER_NOW_MS
    )

    contract: Mapped[Contract] = relationship()
