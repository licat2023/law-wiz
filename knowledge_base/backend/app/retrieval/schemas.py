"""检索条件及上下文请求。"""

from typing import Literal

from pydantic import Field

from app.api.responses import Payload

RetrievalStrategy = Literal["vector", "hybrid", "reranked"]


class SearchRequest(Payload):
    # 默认排除已废止内容，尚未生效的内容在检索时始终过滤。
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    include_abolished: bool = False
    doc_type: str | None = None
    corpus_tier: int | None = None
    strategy: RetrievalStrategy | None = None
    diagnostics: bool = False
