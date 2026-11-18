"""ContractReviewAgent 的薄入口：只负责 Schema 与 Graph 的衔接。"""

from ai_service.agent import AgentContext
from ai_service.review.graph import ContractReviewGraph
from ai_service.review.nodes import ContractReviewNodes
from ai_service.review.schemas import ContractReviewInput, ContractReviewResult


class ContractReviewAgent:
    """将合同和风险规则交给已编译的审查工作流。"""

    def __init__(self, search_laws, llm) -> None:
        self._workflow = ContractReviewGraph(ContractReviewNodes(search_laws, llm)).workflow

    async def invoke(self, input: ContractReviewInput, context: AgentContext) -> ContractReviewResult:
        """运行条款提取、检索与风险分析，返回结构化审查结果。"""
        if not isinstance(input, ContractReviewInput):
            input = ContractReviewInput.model_validate(input)
        state = await self._workflow.ainvoke(
            {
                "plain_text": input.plain_text,
                "context": context,
                "rules": [rule.model_dump() for rule in input.risk_rules],
            }
        )
        return ContractReviewResult(
            extracted_terms=state.get("extracted_terms", {}), risk_points=state.get("risk_points", [])
        )
