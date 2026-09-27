"""Agent 到 Backend Internal API 的唯一出口。"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.schemas.contracts import Citation


class BackendClientError(Exception):
    """网络、非 2xx 或返回结构不符合内部契约时抛出；不含敏感 Token。"""


class _ApiResponse(BaseModel):
    code: int
    data: dict | None = None
    request_id: str | None = None


class BackendClient:
    """唯一 HTTP Client；将服务认证、超时及响应校验集中在此处。"""

    async def retrieve_laws(self, *, query: str, request_id: str, trace_id: str | None) -> list[Citation]:
        if not settings.backend_base_url:
            raise BackendClientError("Backend Internal API 地址未配置")
        if not settings.backend_token:
            raise BackendClientError("Backend Internal API 服务令牌未配置")
        headers = {"X-Internal-Service-Token": settings.backend_token, "X-Request-ID": request_id}
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        try:
            async with httpx.AsyncClient(
                base_url=settings.backend_base_url, timeout=settings.request_timeout_seconds
            ) as client:
                response = await client.get(
                    "/api/v1/internal/legal-qa/laws", params={"q": query}, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise BackendClientError("Backend Internal API 请求超时") from exc
        except httpx.HTTPError as exc:
            raise BackendClientError("无法连接 Backend Internal API") from exc
        if not response.is_success:
            raise BackendClientError(f"Backend Internal API 返回 HTTP {response.status_code}")
        try:
            body = _ApiResponse.model_validate(response.json())
            if body.code != 0 or body.data is None:
                raise BackendClientError("Backend Internal API 返回业务错误")
            items = body.data.get("items", [])
            return [
                Citation(
                    document_id=item.get("document_id"),
                    kb_chunk_id=item.get("chunk_id"),
                    law_name=item.get("law_name"),
                    article_no=item.get("article_no"),
                    quoted_text=item.get("content"),
                    relevance_score=item.get("score"),
                )
                for item in items
            ]
        except (ValidationError, ValueError, TypeError) as exc:
            raise BackendClientError("Backend Internal API 返回结构不合法") from exc


class LawRetrievalTool:
    """对 LangGraph 暴露稳定的法律检索能力，节点无需知道 HTTP 细节。"""

    def __init__(self, client: BackendClient | None = None) -> None:
        self._client = client or BackendClient()

    async def search(self, query: str, *, request_id: str, trace_id: str | None) -> list[Citation]:
        return await self._client.retrieve_laws(query=query, request_id=request_id, trace_id=trace_id)


class FakeLawTool:
    async def search(self, query: str, *, request_id: str, trace_id: str | None) -> list[Citation]:
        return []


class FakeRiskRuleTool:
    async def match(self, plain_text: str) -> list[dict]:
        return []
