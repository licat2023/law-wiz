"""Expose structured review and QA to the business backend over internal HTTP."""

import asyncio
import secrets
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ai_service.agent import AgentContext
from ai_service.config import Settings
from ai_service.errors import InferenceError
from ai_service.knowledge_base import KnowledgeBaseSearch
from ai_service.llm import DeepSeekInvocationError, create_chat_model
from ai_service.qa.agent import LegalQaAgent
from ai_service.qa.schemas import LegalQaInput, LegalQaResult
from ai_service.review.agent import ContractReviewAgent
from ai_service.review.schemas import ContractReviewInput, ContractReviewResult


def create_app(settings: Settings | None = None, *, search_laws=None, model=None) -> FastAPI:
    """Build internal endpoints with isolated model and knowledge base clients."""
    settings = settings or Settings()
    slots = asyncio.Semaphore(settings.max_concurrent)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.environment == "production" and (
            settings.allow_fake_model or len(settings.service_token) < 32
        ):
            raise RuntimeError("生产环境必须配置独立的 AI 服务令牌和真实模型")
        own_model = model is None and not settings.allow_fake_model
        active_model = model
        if own_model:
            active_model = create_chat_model(
                api_key=settings.model_api_key,
                base_url=settings.model_base_url,
                model=settings.model_name,
                timeout=settings.model_timeout_seconds,
            )
        try:
            async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as client:
                retrieval = search_laws or KnowledgeBaseSearch(settings, client).search
                app.state.review = ContractReviewAgent(retrieval, active_model)
                app.state.qa = LegalQaAgent(retrieval, active_model)
                yield
        finally:
            if own_model:
                try:
                    await asyncio.to_thread(active_model.root_client.close)
                finally:
                    await active_model.root_async_client.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(InferenceError)
    async def inference_error(_request: Request, exc: InferenceError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "message": str(exc)}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"code": "invalid_input", "message": "AI 输入结构不合法"}, status_code=422)

    def context(
        authorization: Annotated[str | None, Header()] = None,
        x_request_id: Annotated[str | None, Header(max_length=128)] = None,
        x_trace_id: Annotated[str | None, Header(max_length=128)] = None,
    ) -> AgentContext:
        if not secrets.compare_digest(
            (authorization or "").encode(), f"Bearer {settings.service_token}".encode()
        ):
            raise HTTPException(status_code=401, detail="AI 服务凭据无效")
        return AgentContext(request_id=x_request_id or uuid.uuid4().hex, trace_id=x_trace_id)

    async def invoke[Result](invoke_agent: Callable[[], Awaitable[Result]]) -> Result:
        try:
            async with asyncio.timeout(settings.model_timeout_seconds), slots:
                return await invoke_agent()
        except TimeoutError as exc:
            raise InferenceError(503, "model_unavailable", "AI 推理超时") from exc
        except DeepSeekInvocationError as exc:
            raise InferenceError(503, "model_unavailable", str(exc)) from exc
        except ValidationError as exc:
            raise InferenceError(502, "bad_response", "AI 输入或输出结构不合法") from exc

    @app.get("/internal/health")
    async def health():
        return {"status": "ok"}

    @app.post("/internal/review")
    async def review(
        payload: ContractReviewInput, context: Annotated[AgentContext, Depends(context)]
    ) -> ContractReviewResult:
        return await invoke(lambda: app.state.review.invoke(payload, context))

    @app.post("/internal/qa")
    async def qa(payload: LegalQaInput, context: Annotated[AgentContext, Depends(context)]) -> LegalQaResult:
        return await invoke(lambda: app.state.qa.invoke(payload, context))

    return app
