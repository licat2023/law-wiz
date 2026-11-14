"""异步会话、ORM 基类和空库初始化。"""

import asyncio
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import Settings


def now():
    """以数据库使用的无时区上海本地时间生成时间戳。"""
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def new_id():
    """生成可直接存储并透传给客户端的 UUID 字符串。"""
    return str(uuid4())


class Base(DeclarativeBase):
    """知识库全部 ORM 模型共享的元数据基类。"""

    pass


class Identity:
    """为领域模型提供字符串主键及 Python 侧生成的创建和更新时间。"""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


BODY = Text().with_variant(LONGTEXT(), "mysql")


def database(url: str):
    """创建异步引擎和工厂，保留会话提交前已加载的字段。"""
    engine = create_async_engine(url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def bootstrap():
    # 先加载所有领域模型，再从 Base.metadata 建表。
    """为配置的数据库显式创建缺失表，供空库初始化命令调用。"""
    from app.infrastructure.models import Base

    settings = Settings()
    if not settings.database_url:
        raise ValueError("需要配置 KB_DATABASE_URL")
    engine, _ = database(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap())
