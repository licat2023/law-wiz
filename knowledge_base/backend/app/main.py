"""创建知识库 FastAPI 应用并注册 HTTP 入口。"""

import asyncio
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from starlette.datastructures import Headers

from app.api.auth_router import router as auth_router
from app.config import Settings
from app.documents.router import router as documents_router
from app.errors import AppError
from app.indexing.router import router as indexing_router
from app.infrastructure.database import new_id
from app.knowledge_bases.router import router as knowledge_bases_router
from app.lifespan import lifespan
from app.retrieval.router import router as retrieval_router

logger = logging.getLogger("knowledge_base.api")


class BodyTooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, "请求超过大小上限")


def body_limit_response(state):
    return JSONResponse(
        {"code": 40001, "message": "请求超过大小上限", "data": None, "request_id": state["request_id"]},
        status_code=413,
    )


class BodyLimit:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        allowance = 512 * 1024
        if content_type == "multipart/form-data":
            limit = self.settings.max_upload_bytes + allowance
        elif scope["path"].endswith("/imports"):
            # 迁移包可同时包含恢复全文和原始块；JSON 转义每字符最多 12 字节。
            limit = 24 * self.settings.max_text_chars + allowance
        elif content_type == "application/json" and "/documents" in scope["path"]:
            limit = 12 * self.settings.max_text_chars + allowance
        else:
            limit = allowance
        length = headers.get("content-length", "")
        if length.isdecimal() and len(length) <= 12 and int(length) > limit:
            await body_limit_response(scope["state"])(scope, receive, send)
            return
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            event = await receive()
            if event["type"] == "http.request":
                consumed += len(event.get("body", b""))
                if consumed > limit:
                    raise BodyTooLarge()
            return event

        await self.app(scope, bounded_receive, send)


def create_app(settings: Settings | None = None):
    settings = settings or Settings()

    app = FastAPI(title="独立知识库", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(BodyLimit, settings=settings)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        )

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = new_id()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(AppError)
    async def business_error(request, exc):
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "data": None, "request_id": request.state.request_id},
            status_code=exc.status,
        )

    @app.exception_handler(BodyTooLarge)
    async def body_too_large(request, exc):
        return body_limit_response(request.scope["state"])

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "code": 40001,
                "message": "请求参数不合法，请检查必填项和取值范围",
                "data": None,
                "request_id": request.state.request_id,
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled(request, exc):
        logger.error("请求失败 %s (%s)", request.state.request_id, type(exc).__name__)
        return JSONResponse(
            {
                "code": 50000,
                "message": "服务暂不可用，请稍后重试",
                "data": None,
                "request_id": request.state.request_id,
            },
            status_code=500,
        )

    @app.get("/api/health")
    async def health(request: Request):
        return {"code": 0, "data": {"status": "ok"}, "request_id": request.state.request_id}

    @app.get("/api/ready")
    async def ready(request: Request):
        async with app.state.sessions() as db:
            await db.execute(text("SELECT 1"))
        await asyncio.to_thread(app.state.vector.heartbeat)
        return {
            "code": 0,
            "data": {"status": "ready", "embedding_mode": settings.embedding_mode},
            "request_id": request.state.request_id,
        }

    for router in (auth_router, knowledge_bases_router, documents_router, indexing_router, retrieval_router):
        app.include_router(router)
    return app


app = create_app()
