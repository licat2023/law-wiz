"""知识库创建和设置的请求模型。"""

from pydantic import ConfigDict, Field, field_validator

from app.api.responses import Payload
from app.indexing.chunking import ChunkOptions


class KnowledgeBaseCreate(ChunkOptions):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    application_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("名称不能为空")
        return value.strip()


class KnowledgeBasePatch(Payload):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    chunking_strategy: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    hierarchical_index: bool | None = None
    semantic_threshold: float | None = None
