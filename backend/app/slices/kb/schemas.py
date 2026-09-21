"""知识库切片的对外契约（Pydantic 模型）。

字段与 05-接口设计 §5.5 的 D-01 ~ D-05 一致；ID 一律为**字符串**（§3.4）。

⚠️ **与文档示例的一处差异**：D-01 的响应示例里 `chunk_count` 为 `0`
（暗示"索引时才切分"）。但 `04-数据库设计` 的 `kb_document` **没有存放语料全文的列** ——
全文只存在于 `kb_chunk.content`。若创建时不落块，索引阶段就无据可切。
因此本项目在**创建时即完成切分**，`chunk_count` 返回真实值，`index_status`
仍为 `pending`（表示**尚未向量化**）。
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["law", "interpretation", "case", "template"]


class CreateDocumentRequest(BaseModel):
    """D-01 请求体。"""

    doc_type: DocType
    corpus_tier: int = Field(default=1, ge=1, le=3)
    title: str = Field(min_length=1, max_length=300)
    law_name: str | None = Field(default=None, max_length=200)
    article_no: str | None = Field(default=None, max_length=64)
    chapter_path: str | None = Field(default=None, max_length=300)
    effective_date: dt.date | None = None
    abolished_date: dt.date | None = None
    revision: str | None = Field(default=None, max_length=32)
    source: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=512)
    content: str = Field(min_length=1, description="语料全文，content_hash 由后端计算")


class DocumentCreatedData(BaseModel):
    document_id: str
    content_hash: str
    char_count: int
    index_status: str
    chunk_count: int


class IndexRequest(BaseModel):
    """D-02 请求体。"""

    force: bool = Field(default=False, description="为 true 时对已索引的语料重新向量化")


class IndexTriggeredData(BaseModel):
    """D-02 响应。

    ⚠️ `task_id` 取 `document_id`：`04-数据库设计` 的 15 张表中**没有索引任务表**，
    索引以文档为单位，故任务标识即文档标识。
    """

    document_id: str
    index_status: str
    task_id: str


class DocumentListItem(BaseModel):
    """D-03 列表项。"""

    document_id: str
    doc_type: str
    corpus_tier: int
    title: str
    law_name: str | None = None
    article_no: str | None = None
    effective_date: str | None = None
    index_status: str
    chunk_count: int
    created_at: str


class ChunkItem(BaseModel):
    """D-04 的分块摘要。"""

    chunk_no: int
    chunk_type: str
    article_no: str | None = None
    char_start: int
    char_end: int
    content: str


class DocumentDetailData(BaseModel):
    document_id: str
    doc_type: str
    corpus_tier: int
    title: str
    law_name: str | None = None
    article_no: str | None = None
    chapter_path: str | None = None
    effective_date: str | None = None
    abolished_date: str | None = None
    revision: str | None = None
    source: str | None = None
    source_url: str | None = None
    content_hash: str
    char_count: int | None = None
    index_status: str
    indexed_at: str | None = None
    chunk_count: int
    created_at: str
    content: str = Field(description="由分块按序拼接重建，分块间隙的空白不可还原")
    chunks: list[ChunkItem]


class KbSearchItem(BaseModel):
    """D-05 检索命中的分块。"""

    chunk_id: str
    document_id: str
    law_name: str | None = None
    article_no: str | None = None
    chunk_type: str
    content: str
    effective_date: str | None = None
    score: float
    char_start: int
    char_end: int


class KbSearchData(BaseModel):
    query: str
    items: list[KbSearchItem]
