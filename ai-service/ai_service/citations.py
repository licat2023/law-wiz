"""业务后端内部使用的知识库引用快照。"""

from pydantic import BaseModel, Field


# 保存命中文档、分块和索引修订标识，并携带可展示的引用文本。
class Citation(BaseModel):
    knowledge_base_id: str | None = None
    revision: str | None = None
    index_revision_id: str | None = None
    title: str | None = None
    document_id: str | None = None
    knowledge_base_chunk_id: str | None = None
    law_name: str | None = None
    article_no: str | None = None
    quoted_text: str | None = None
    relevance_score: float | None = None
    # 检索文档类型供 Agent 区分模板和法律依据，不写入引用快照。
    document_type: str | None = Field(default=None, exclude=True)
