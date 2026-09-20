"""用户与账户模型（M1，P1）。

对应 04-数据库设计 §5.1 / §5.2。

⚠️ **`user` 表硬删除，不用 `SoftDeleteMixin`**（见 ADR-0007）。
`phone` / `email` 是**普通唯一索引**，绝不可改成 `(phone, deleted_at)` ——
MySQL 的唯一索引不约束 NULL，那样会让唯一性完全失效。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import (
    BIGINT_PK,
    DATETIME_MS,
    MYSQL_TABLE_ARGS,
    Base,
    TimestampMixin,
    fk,
)


class User(Base, TimestampMixin):
    """用户账户。

    一期只有个人与企业两种 `account_type`，但**企业主体与成员管理属 P3**，
    因此一期不做多成员归属关系（见 03-概要设计 §3.2 功能点分期对照表）。
    """

    __tablename__ = "user"
    __table_args__ = (
        UniqueConstraint("phone", name="uk_user_phone"),
        UniqueConstraint("email", name="uk_user_email"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True, default=None)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="personal", server_default="personal"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)

    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserProfile(Base, TimestampMixin):
    """用户扩展资料。

    ⚠️ `real_name` **仅用于展示**。实名认证是 P3 的独立流程（M7-05），
    其结果与证书绑定另行建表，**不混入本表**（见 04-数据库设计 §5.2）。
    """

    __tablename__ = "user_profile"
    __table_args__ = (
        UniqueConstraint("user_id", name="uk_user_profile_user"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("user.id", name="fk_user_profile_user"), nullable=False
    )
    real_name: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    org_name: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    org_role: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    avatar_object_id: Mapped[int | None] = mapped_column(BIGINT_PK, nullable=True, default=None)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)

    user: Mapped[User] = relationship(back_populates="profile")
