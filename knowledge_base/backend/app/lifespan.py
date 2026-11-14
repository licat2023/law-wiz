"""知识库数据库、向量、嵌入客户端和任务处理器的生命周期。"""

import asyncio
import contextlib
from contextlib import asynccontextmanager

import httpx

from app.api.auth import parse_grants
from app.indexing.jobs import Processor
from app.infrastructure.database import database
from app.infrastructure.embedding import DevelopmentEmbedding, RemoteEmbedding
from app.infrastructure.models import Base
from app.infrastructure.vector_store import VectorStore


@asynccontextmanager
async def lifespan(app):
    """启动时建立依赖并可选启动处理器，退出时先等待处理器取消再释放连接。"""
    settings = app.state.settings
    settings.check_runtime()
    app.state.grants = parse_grants(settings)
    # 独立解析入口在进程内一次处理一个文件，避免多份解析缓冲同时占用内存。
    app.state.parse_gate = asyncio.Semaphore(1)
    await asyncio.to_thread((settings.data_root / "files").mkdir, parents=True, exist_ok=True)
    engine, app.state.sessions = database(settings.database_url)
    client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    worker = None
    try:
        if settings.auto_create_schema:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        app.state.embedding = (
            DevelopmentEmbedding()
            if settings.embedding_mode == "development"
            else RemoteEmbedding(
                client,
                settings.embedding_base_url,
                settings.embedding_api_key,
                settings.embedding_model,
                settings.embedding_dimensions,
            )
        )
        app.state.vector = await asyncio.to_thread(VectorStore, settings.data_root / "chroma")
        app.state.processor = Processor(app.state)
        if settings.worker_enabled:
            worker = asyncio.create_task(app.state.processor.loop())
        yield
    finally:
        if worker:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        await client.aclose()
        await engine.dispose()
