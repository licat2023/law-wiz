"""文档上传、修订和历史导入的输入。"""

from typing import Any

from pydantic import Field

from app.api.responses import Payload


class MarkdownCreate(Payload):
    # 元数据随初始正文修订保存，解析后的正文长度另受运行配置限制。
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=10_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentPatch(Payload):
    # revision 是调用方所读到的修订号，metadata 提供时替换整份元数据。
    revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, min_length=1, max_length=10_000_000)
    metadata: dict[str, Any] | None = None


class ImportRequest(Payload):
    # 迁移可保留只有历史引用、缺失可恢复正文的旧文档。
    source_namespace: str = Field(min_length=1, max_length=100)
    source_document_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=10_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    history_chunks: list[dict[str, Any]] = Field(default_factory=list, max_length=10000)
