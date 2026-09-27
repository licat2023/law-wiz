from typing import TypedDict

from app.schemas.contracts import AgentContext, Citation


class LegalQaState(TypedDict, total=False):
    question: str
    context: AgentContext
    sources: list[Citation]
    answer: str
