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
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def new_id():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


BODY = Text().with_variant(LONGTEXT(), "mysql")


def database(url: str):
    engine = create_async_engine(url, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def bootstrap():
    # 先加载所有领域模型，再从 Base.metadata 建表。
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
