"""数据库基类与通用列约定。

对应 04-数据库设计 §2.2 / §2.3。

**三条刻意为之的规范**（理由见 04-数据库设计 §2.2）：
- 枚举用 `VARCHAR` 而非 MySQL `ENUM`；
- 不使用触发器与存储过程；
- 金额一律 `DECIMAL(18,2)`，禁止浮点。

**方言相关类型的处理模式（本文件统一负责）**：

MySQL 特有的类型（`DATETIME(3)` 的毫秒精度、`LONGTEXT`、`MEDIUMTEXT`、`JSON`）
在 SQLAlchemy 通用类型中没有对应物，而单元测试跑在 SQLite 上（为了零依赖），
MySQL 方言类型在 SQLite 下**无法建表**。

因此统一用 `with_variant` 表达：**MySQL 上用精确类型，其他方言退化为通用类型**。
这样同一套模型既能在生产用上 MySQL 的精确类型，又能在测试里建表 ——
**不需要为测试单独维护一份 DDL**（手写两套 DDL 必然会漂移）。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, MetaData, Text, func
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 统一命名约定：使 Alembic 自动生成的迁移脚本有稳定、可读的约束名。
# 否则匿名约束在不同环境会拿到不同名字，迁移无法对齐。
NAMING_CONVENTION = {
    "ix": "idx_%(table_name)s_%(column_0_N_name)s",
    "uq": "uk_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    # 外键名由模型中的 ForeignKey(..., name="...") **显式指定**，不依赖本约定 ——
    # 因为约定里没有"被引用表名"这个 token（%(related_table_name)s 会 KeyError），
    # 而 %(column_0_name)s 会生成 `fk_contract_version_contract_id`，与 04 文档不符。
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

# MySQL 需显式指定字符集与排序规则，与 04-数据库设计 §2.1 一致
MYSQL_TABLE_ARGS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}

# ---- 方言相关类型 ----

# 主键与外键：04-数据库设计 §2.2 规定主键一律 BIGINT UNSIGNED。
# ⚠️ 若不显式指定而依赖类型注解推断，SQLAlchemy 会渲染成 INTEGER，与设计不符。
#
# SQLite 上必须显式退化为 INTEGER（**不是 BIGINT**）：SQLite 只有声明为
# `INTEGER PRIMARY KEY` 的列才是 rowid 别名、才能自增；声明成 BIGINT 会导致
# `NOT NULL constraint failed: user.id`。
BIGINT_PK = BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql").with_variant(Integer(), "sqlite")

# ---- 外键工厂 ----


# 外键约束名必须**显式指定**，不能靠命名约定：SQLAlchemy 的 FK 约定里没有
# "被引用表名"这个 token（`%(related_table_name)s` 会 KeyError），而
# `%(column_0_name)s` 会生成 `fk_contract_version_contract_id`，
# 与 `04-数据库设计` §6.2 定下的 `fk_contract_version_contract` 不符。
#
# 用法：`owner_id: Mapped[int] = mapped_column(BIGINT_PK, fk("user.id", name="fk_contract_owner"), nullable=False)`
def fk(target: str, *, name: str | None = None) -> ForeignKey:
    """构造外键。`target` 形如 `"user.id"`。"""
    return ForeignKey(target, name=name)


# 毫秒精度时间戳：MySQL 用 DATETIME(3)，其他方言退化为 DATETIME
DATETIME_MS = DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")

# 大文本：MySQL 用 LONGTEXT（合同全文可能很长），其他方言退化为 TEXT
LONGTEXT_V = Text().with_variant(mysql.LONGTEXT(), "mysql")

# 中等文本：MySQL 用 MEDIUMTEXT（问答消息），其他方言退化为 TEXT
MEDIUMTEXT_V = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


# JSON：MySQL 8 有原生 JSON 类型（可索引、可校验），其他方言退化为 TEXT
def _json_type():
    """延迟构造，避免在非 MySQL 环境下导入方言 JSON。"""
    from sqlalchemy import JSON

    return JSON().with_variant(mysql.JSON(), "mysql")


JSON_V = _json_type()

# 时区策略：统一使用 DATETIME(3) 存**北京时间（UTC+8）**，由应用层保证；
# **不使用 TIMESTAMP**，避免会话时区导致的隐式转换（04-数据库设计 §2.1）。
#
# ⚠️ 服务端默认值必须**按方言渲染成不同形式**，这是实测结论：
#   - MySQL 9.7.2：`DATETIME(3) DEFAULT CURRENT_TIMESTAMP`（不带精度）会报
#     `ERROR 1067 Invalid default value` —— 带 fsp 的列，默认值也必须带 fsp；
#   - SQLite：只认 `CURRENT_TIMESTAMP`，不认带参数的写法。
#
# 用 `func.now(3)` 一次满足两者：SQLAlchemy 按方言渲染，
# **MySQL → `now(3)`（实测为毫秒精度），SQLite → `CURRENT_TIMESTAMP`**。
SERVER_NOW_MS = func.now(3)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """通用时间字段。对应 04-数据库设计 §2.3。"""

    created_at: Mapped[dt.datetime] = mapped_column(DATETIME_MS, nullable=False, server_default=SERVER_NOW_MS)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DATETIME_MS,
        nullable=False,
        server_default=SERVER_NOW_MS,
        server_onupdate=SERVER_NOW_MS,
    )


class SoftDeleteOnlyMixin:
    """只有软删除字段、没有时间字段的表（如 `user_profile`）用这个。"""

    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)


class SoftDeleteMixin(TimestampMixin):
    """软删除标记（含通用时间字段）。

    ⚠️ **只用于需要保留历史的表**（contract、contract_version、review_task、
    kb_document、qa_session、file_object）。`user` 表**不使用**本 Mixin ——
    它采用硬删除，理由见 ADR-0007：《个人信息保护法》下注销时保留手机号与邮箱
    是隐私风险。

    ⛔ **绝不可把 `deleted_at` 放进唯一索引**：MySQL 的唯一索引不约束 NULL，
    `deleted_at IS NULL` 的行会完全不受唯一性保护。实测证据见 ADR-0007。
    """

    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)
