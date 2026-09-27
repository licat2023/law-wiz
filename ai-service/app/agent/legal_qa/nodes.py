from app.agent.legal_qa.prompts import LEGAL_QA_PROMPT
from app.agent.legal_qa.state import LegalQaState
from app.llm.deepseek import invoke_chat


class LegalQaNodes:
    def __init__(self, law_tool, llm=None) -> None:
        self._law_tool = law_tool
        self._llm = llm

    async def prepare_query(self, state: LegalQaState) -> LegalQaState:
        return state

    async def retrieve_law(self, state: LegalQaState) -> LegalQaState:
        context = state["context"]
        return {
            "sources": await self._law_tool.search(
                state["question"], request_id=context.request_id, trace_id=context.trace_id
            )
        }

    async def generate_answer(self, state: LegalQaState) -> LegalQaState:
        messages = LEGAL_QA_PROMPT.format_messages(question=state["question"], sources=state.get("sources", []))
        if not state.get("sources"):
            return {"answer": "未找到直接法律依据，无法给出确定性回答。"}
        if self._llm is not None:
            response = await invoke_chat(self._llm, messages)
            content = response.content if isinstance(response.content, str) else ""
            if content.strip():
                return {"answer": content.strip()}
        return {"answer": f"依据已检索到的法律材料，针对“{state['question']}”应结合具体合同事实判断。"}

    async def validate_citations(self, state: LegalQaState) -> LegalQaState:
        # 只保留能够回溯到 Backend 知识库记录的来源；模型不能自行编造引用。
        sources = [
            source
            for source in state.get("sources", [])
            if source.document_id and source.kb_chunk_id and source.quoted_text
        ]
        return {"sources": sources}

    async def finalize(self, state: LegalQaState) -> LegalQaState:
        return state
