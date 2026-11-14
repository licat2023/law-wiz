"""检索条件及上下文请求。"""

from pydantic import Field

from app.api.responses import Payload


class SearchRequest(Payload):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    include_abolished: bool = False
    doc_type: str | None = None
    corpus_tier: int | None = None
