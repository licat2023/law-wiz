"""定义 Agent 工作流状态。"""

from typing import TypedDict

from ai_service.agent import AgentContext
from ai_service.citations import Citation
from ai_service.review.schemas import RiskPoint


class ContractReviewState(TypedDict, total=False):
    """审查节点逐步补充的共享状态，各节点只需返回本阶段更新的字段。"""

    plain_text: str
    context: AgentContext
    extracted_terms: dict
    laws: list[Citation]
    rules: list[dict]
    risk_points: list[RiskPoint]
