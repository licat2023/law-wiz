"""法律问答 Agent 的调用入口。"""

from ai_service.agent import AgentContext
from ai_service.qa.graph import LegalQaGraph
from ai_service.qa.nodes import LegalQaNodes
from ai_service.qa.schemas import LegalQaInput, LegalQaResult
from ai_service.qa.state import AnswerDelta


class LegalQaAgent:
    """将问题交给已编译的问答工作流并返回回答与引用快照。"""

    def __init__(self, search_laws, llm=None) -> None:
        self._graph = LegalQaGraph(LegalQaNodes(search_laws, llm)).workflow

    async def invoke(
        self, input: LegalQaInput, context: AgentContext, *, emit: AnswerDelta | None = None
    ) -> LegalQaResult:
        """生成本轮结果，可在引用校验前逐段发布答复正文。"""
        if not isinstance(input, LegalQaInput):
            input = LegalQaInput.model_validate(input)
        state = await self._graph.ainvoke(
            {
                "question": input.question,
                "context": context,
                "report": input.report,
                "history": input.history,
                "emit": emit,
            }
        )
        return LegalQaResult(
            answer=state["answer"], citations=state.get("sources", []), model_name=state.get("model_name")
        )
