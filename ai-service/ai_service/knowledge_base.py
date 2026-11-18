"""Retrieve verifiable citations from the inference service's read-only knowledge base."""

import asyncio
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, ValidationError

from ai_service.citations import Citation
from ai_service.config import Settings
from ai_service.errors import InferenceError


class _Hit(BaseModel):
    knowledge_base_id: str
    document_id: str
    revision: int | str
    index_revision_id: str
    chunk_id: str
    title: str
    content: str
    score: float
    parent_content: str | None = None
    article_chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class _SearchData(BaseModel):
    items: list[_Hit]
    article_contents: dict[str, str] = Field(default_factory=dict)
    article_limit_reached: bool = False


class KnowledgeBaseSearch:
    """Resolve and deduplicate citations against the configured knowledge base."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    async def _request(self, query: str, headers: dict[str, str]) -> dict:
        settings = self.settings
        if not all(
            (
                settings.knowledge_base_base_url,
                settings.knowledge_base_default_id,
                settings.knowledge_base_service_key,
            )
        ):
            raise InferenceError(503, "knowledge_unavailable", "知识库检索未配置")
        base = settings.knowledge_base_base_url.rstrip("/")
        index = quote(settings.knowledge_base_default_id, safe="")
        url = f"{base}/api/knowledge-bases/{index}/search"
        headers["Authorization"] = f"Bearer {settings.knowledge_base_service_key}"
        try:
            try:
                response = await self.client.post(url, json={"query": query, "top_k": 5}, headers=headers)
            except httpx.ConnectError, httpx.ConnectTimeout:
                await asyncio.sleep(0.05)
                response = await self.client.post(url, json={"query": query, "top_k": 5}, headers=headers)
            if response.status_code == 404:
                raise InferenceError(404, "knowledge_not_found", "知识文档不存在")
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or body.get("code") != 0 or not isinstance(body.get("data"), dict):
                raise ValueError("Invalid search response")
            return body["data"]
        except (httpx.HTTPError, ValueError) as exc:
            raise InferenceError(503, "knowledge_unavailable", "知识库服务暂不可用") from exc

    async def search(self, query: str, *, request_id: str, trace_id: str | None = None) -> list[Citation]:
        """校验命中范围，以完整法条替换已定位到法条的摘录，再按法条去重。"""
        headers = {"X-Request-ID": request_id}
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        result = await self._request(query, headers)
        try:
            data = _SearchData.model_validate(result)
            if any(hit.knowledge_base_id != self.settings.knowledge_base_default_id for hit in data.items):
                raise ValueError("知识库响应超出授权范围")
            if data.article_limit_reached and not data.items:
                raise ValueError("命中法条超过完整引用长度上限")
            citations = []
            seen_articles = set()
            for hit in data.items:
                quoted_text = hit.parent_content or hit.content
                document_type = hit.metadata.get("doc_type")
                if hit.article_chunk_id:
                    quoted_text = data.article_contents[hit.article_chunk_id]
                    if not quoted_text.strip():
                        raise ValueError("知识库未返回完整法条")
                    if hit.article_chunk_id in seen_articles:
                        continue
                    seen_articles.add(hit.article_chunk_id)
                citations.append(
                    Citation(
                        document_id=hit.document_id,
                        knowledge_base_chunk_id=hit.chunk_id,
                        knowledge_base_id=hit.knowledge_base_id,
                        revision=str(hit.revision),
                        index_revision_id=hit.index_revision_id,
                        title=hit.title,
                        law_name=hit.metadata.get("law_name") or hit.title,
                        article_no=hit.metadata.get("article_no"),
                        quoted_text=quoted_text,
                        relevance_score=hit.score,
                        document_type=document_type if isinstance(document_type, str) else None,
                    )
                )
            return citations
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise InferenceError(503, "knowledge_unavailable", "知识库引用响应不合法") from exc
