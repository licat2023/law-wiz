"""建立索引的请求模型。"""

from pydantic import Field

from app.api.responses import Payload


class IndexRequest(Payload):
    revision: int = Field(ge=1)
    chunking_strategy: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    hierarchical_index: bool | None = None
    semantic_threshold: float | None = None
