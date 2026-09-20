"""数据库会话管理。

服务器内存极紧（1.7 GiB，可用约 950 MiB），因此连接池刻意设小。
池大小由配置控制，不用默认值。
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    echo=_settings.db_echo,
    pool_pre_ping=True,  # 防止取到已被服务端关闭的连接（MySQL wait_timeout）
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_recycle=_settings.db_pool_recycle,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    """FastAPI 依赖：每请求一个会话，请求结束即关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session]:
    """脚本与后台任务用的会话上下文：正常提交，异常回滚。

    后台异步任务（审查、向量化）不在请求生命周期内，因此不能用 `get_db`。
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
