"""定义 Agent 工作流状态。"""

from collections.abc import Awaitable, Callable
from typing import TypedDict

from ai_service.agent import AgentContext
from ai_service.citations import Citation
from ai_service.qa.report import ReviewFollowupContext
from ai_service.qa.schemas import RecentTurnMessage

type AnswerDelta = Callable[[str], Awaitable[None]]


class LegalQaState(TypedDict, total=False):
    """问答节点逐步填充的状态，包含本次检索来源和生成结果。"""

    question: str
    context: AgentContext
    report: ReviewFollowupContext | None
    history: list[RecentTurnMessage]
    sources: list[Citation]
    retrieval_unavailable: bool
    emit: AnswerDelta | None
    answer: str
    model_name: str | None
