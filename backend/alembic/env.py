"""Alembic 迁移环境。

两个要点：

1. **连接串从应用配置读取**（`app.core.config`），不写在 `alembic.ini` 里 ——
   否则凭据会进版本库，违反 02-技术栈 §4.2。
2. **必须导入 `app.models`**，使 `Base.metadata` 含有全部表。
   漏导入任何一张表都会让 `--autogenerate` **静默漏表**，且要到建库时才发现。
   `app/models/__init__.py` 已统一导出，此处只需导入该包。
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401  确保所有模型注册到 Base.metadata

# 导入应用配置与全部模型
from app.core.config import get_settings
from app.infra.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 从应用配置注入连接串（覆盖 alembic.ini 中的空值）
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata

# 由迁移脚本**手工维护**的外键：`contract.current_version_id` → `contract_version.id`。
# 它是循环外键（两张表互相引用），无法在模型里用普通 ForeignKey 声明 ——
# 否则 `Base.metadata.create_all()` 在 SQLite（测试用）上会生成
# `ALTER TABLE ... ADD CONSTRAINT`，而 SQLite 不支持这种语法。
# 因此模型里不声明它，改由初始迁移建表后单独 ALTER 添加。
# 若不在此排除，**每次 autogenerate 都会生成一条 drop**，把该约束删掉。
_HAND_MANAGED_FOREIGN_KEYS = {"fk_contract_current_version"}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "foreign_key_constraint" and name in _HAND_MANAGED_FOREIGN_KEYS)


# ⚠️ `compare_server_default=False` 是**有意为之**。
# 我们的时间戳默认值是 `SERVER_NOW_MS = func.now(3)`，它在 MySQL 上渲染为 `now(3)`，
# 而 MySQL 反过来报告的是 `CURRENT_TIMESTAMP(3)`。两者功能等价但文本不同，
# 打开该项比较会让**每次 autogenerate 都多出约 20 条无意义的 `alter_column`**，
# 掩盖真正的变更。代价是：以后若真的改了某列的 server_default，需要手工写迁移。
_COMPARE_OPTS = {
    "compare_type": True,
    "compare_server_default": False,
    "include_object": include_object,
}


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连库。用于人工审核与 DBA 执行。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_COMPARE_OPTS,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        **_COMPARE_OPTS,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式：用异步引擎连接（与应用同栈：`mysql+aiomysql`）。"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        # 迁移脚本本身是同步的，交给 run_sync 在绿色线程里执行
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
