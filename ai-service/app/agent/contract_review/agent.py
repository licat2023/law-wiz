"""ContractReviewAgent 的薄入口：只负责 Schema 与 Graph 的衔接。"""

from app.agent.contract_review.graph import ContractReviewGraph
from app.agent.contract_review.nodes import ContractReviewNodes
from app.agent.core.base_agent import BaseAgent
from app.schemas.contracts import AgentContext, ContractReviewInput, ContractReviewResult


class ContractReviewAgent(BaseAgent):
    def __init__(self, law_tool, risk_rule_tool, llm=None) -> None:
        self._workflow = ContractReviewGraph(ContractReviewNodes(law_tool, risk_rule_tool, llm)).workflow

    async def invoke(self, input: ContractReviewInput, context: AgentContext) -> ContractReviewResult:
        if not isinstance(input, ContractReviewInput):
            input = ContractReviewInput.model_validate(input)
        state = await self._workflow.ainvoke({"plain_text": input.plain_text, "context": context})
        return ContractReviewResult(
            extracted_terms=state.get("extracted_terms", {}), risk_points=state.get("risk_points", [])
        )
