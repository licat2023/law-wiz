from typing import TypedDict

from app.schemas.contracts import AgentContext, RiskPoint


class ContractReviewState(TypedDict, total=False):
    plain_text: str
    context: AgentContext
    extracted_terms: dict
    laws: list[dict]
    rules: list[dict]
    risk_points: list[RiskPoint]
