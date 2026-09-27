from app.agent.core.base_agent import BaseAgent
from app.agent.legal_qa.graph import LegalQaGraph
from app.agent.legal_qa.nodes import LegalQaNodes
from app.schemas.contracts import AgentContext, LegalQaInput, LegalQaResult


class LegalQaAgent(BaseAgent):
    def __init__(self, law_tool, llm=None) -> None:
        self._graph = LegalQaGraph(LegalQaNodes(law_tool, llm)).workflow

    async def invoke(self, input: LegalQaInput, context: AgentContext) -> LegalQaResult:
        # Runtime 的通用入口接收 dict；在业务 Agent 边界完成具体输入契约校验。
        if not isinstance(input, LegalQaInput):
            input = LegalQaInput.model_validate(input)
        state = await self._graph.ainvoke({"question": input.question, "context": context})
        return LegalQaResult(answer=state["answer"], citations=state.get("sources", []))
