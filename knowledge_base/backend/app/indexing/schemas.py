"""建立索引的请求模型。"""

from pydantic import Field

from app.api.responses import Payload


class IndexRequest(Payload):
    # 未提供的切分选项沿用库默认配置，合并后统一校验。
    revision: int = Field(ge=1)
    chunking_strategy: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    hierarchical_index: bool | None = None
    semantic_threshold: float | None = None
