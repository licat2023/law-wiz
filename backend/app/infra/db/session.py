"""数据库会话管理（异步栈）。

服务器内存极紧（1.7 GiB，可用约 950 MiB），因此连接池刻意设小。
池大小由配置控制，不用默认值。

**异步**：引擎与会话都用 `aiomysql` 驱动 / `AsyncSession`，路由与后台任务
一律 `await` 访问数据库。⚠️ 任何一处写成同步 `Session` 都会在请求处理时
阻塞事件循环 —— 换驱动时 `database_url` 也必须同步改（core/config.py）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=_settings.db_echo,
    pool_pre_ping=True,  # 防止取到已被服务端关闭的连接（MySQL wait_timeout）
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_recycle=_settings.db_pool_recycle,
)

SessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI 依赖：每请求一个会话，请求结束即关闭。"""
    async with SessionLocal() as db:
        yield db


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    """脚本与后台任务用的会话上下文：正常提交，异常回滚。

    后台异步任务（审查、向量化）不在请求生命周期内，因此不能用 `get_db`。
    """
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
