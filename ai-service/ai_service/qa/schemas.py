"""法律问答 Agent 的输入与输出。"""

from typing import Literal

from pydantic import BaseModel, Field, StrictInt

from ai_service.citations import Citation
from ai_service.qa.report import ReviewFollowupContext


class RecentTurnMessage(BaseModel):
    """报告追问提示词携带的一条已完成历史消息。"""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=600)


class LegalQaInput(BaseModel):
    """当前问题及经业务层校验和截断的报告上下文。"""

    question: str = Field(min_length=1, max_length=4000)
    report: ReviewFollowupContext | None = None
    history: list[RecentTurnMessage] = Field(default_factory=list, max_length=6)


class FollowupAnswer(BaseModel):
    """模型输出的建议和实际使用的当轮候选编号。"""

    answer: str = Field(min_length=1, max_length=12000)
    citations: list[StrictInt] = Field(max_length=5, strict=True)


# 返回回答和检索来源快照；未使用真实模型时可省略模型名称。
class LegalQaResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    model_name: str | None = None
