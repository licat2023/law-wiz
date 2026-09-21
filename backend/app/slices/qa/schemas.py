"""问答切片的对外契约（Pydantic 模型）。

字段与 05-接口设计 §5.6 的 E-01 ~ E-05 一致；ID 一律为**字符串**（§3.4）。

⚠️ **回答溯源是本组的核心**：`has_citation = false` 表示"未找到直接法律依据"，
前端必须据此提示用户，而不是让所有回答看起来同样有据可依。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.errors import Page


class CreateSessionRequest(BaseModel):
    """E-01 请求体。`title` 可省，缺省时由首条提问生成。"""

    title: str | None = Field(default=None, max_length=200)


class SessionData(BaseModel):
    """E-01 响应。"""

    session_id: str
    title: str | None = None
    status: str
    message_count: int
    created_at: str


class SessionListItem(BaseModel):
    """E-02 列表项。"""

    session_id: str
    title: str | None = None
    status: str
    message_count: int
    last_message_at: str | None = None
    created_at: str


class CitationItem(BaseModel):
    """回答引用的法条分块。**"回答溯源"的全部数据基础。**"""

    document_id: str | None = None
    kb_chunk_id: str | None = None
    law_name: str | None = None
    article_no: str | None = None
    quoted_text: str | None = None
    relevance_score: float | None = None


class MessageItem(BaseModel):
    """会话中的一条消息。仅 assistant 消息带 `citations`。"""

    message_id: str
    role: str
    content: str
    has_citation: bool
    citations: list[CitationItem] = Field(default_factory=list)
    model_name: str | None = None
    latency_ms: int | None = None
    created_at: str


class SessionDetailData(BaseModel):
    """E-03 响应：会话元信息 + 消息分页。"""

    session_id: str
    title: str | None = None
    status: str
    messages: Page[MessageItem]


class AskRequest(BaseModel):
    """E-04 请求体。"""

    content: str = Field(min_length=1, max_length=4000)


class AskData(BaseModel):
    """E-04 响应（HTTP 202）。

    ⚠️ `assistant_message_id` **预分配**：前端据此先在界面上占位
    （显示"正在思考…"），拿到结果后按 ID 原地替换，避免消息顺序错乱。
    """

    user_message_id: str
    assistant_message_id: str
    status: str
