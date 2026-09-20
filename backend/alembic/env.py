"""Alembic 迁移环境。

两个要点：

1. **连接串从应用配置读取**（`app.core.config`），不写在 `alembic.ini` 里 ——
   否则凭据会进版本库，违反 02-技术栈 §4.2。
2. **必须导入 `app.models`**，使 `Base.metadata` 含有全部表。
   漏导入任何一张表都会让 `--autogenerate` **静默漏表**，且要到建库时才发现。
   `app/models/__init__.py` 已统一导出，此处只需导入该包。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

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


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连库。用于人工审核与 DBA 执行。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # 打开类型与默认值比较，否则改了列类型/默认值不会生成迁移
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
