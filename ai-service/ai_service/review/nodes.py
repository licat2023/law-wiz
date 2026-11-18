"""实现 Agent 工作流各步骤。"""

from ai_service.llm import DeepSeekInvocationError, invoke_chat
from ai_service.review.prompts import (
    CONTRACT_RISK_ANALYSIS_PROMPT,
    CONTRACT_TERM_EXTRACTION_PROMPT,
)
from ai_service.review.schemas import ContractRiskAnalysis, ContractTerms, RiskPoint
from ai_service.review.state import ContractReviewState


class ContractReviewNodes:
    """处理审查工作流节点，使用注入的法律检索和模型客户端。"""

    def __init__(self, search_laws, llm) -> None:
        self._search_laws = search_laws
        self._llm = llm

    async def extract_terms(self, state: ContractReviewState) -> ContractReviewState:
        """从合同开头最多 12000 字符提取结构化条款；模型替身只返回文本长度。"""
        if self._llm is not None:
            # 使用当前 DeepSeek 接入支持的 `json_object` 响应模式，
            # 再将提示词要求的 JSON 解析为 `ContractTerms`。
            output = await invoke_chat(
                self._llm.with_structured_output(ContractTerms, method="json_mode"),
                f"{CONTRACT_TERM_EXTRACTION_PROMPT}\n\n合同全文：\n{state['plain_text'][:12000]}",
            )
            return {"extracted_terms": output.model_dump()}
        return {"extracted_terms": {"text_length": len(state["plain_text"])}}

    async def retrieve_laws(self, state: ContractReviewState) -> ContractReviewState:
        """用合同开头 200 字符检索法条，并传递本次审查的追踪标识。"""
        context = state["context"]
        return {
            "laws": await self._search_laws(
                state["plain_text"][:200], request_id=context.request_id, trace_id=context.trace_id
            )
        }

    async def analyze_risks(self, state: ContractReviewState) -> ContractReviewState:
        """校验法条引用是否在本次检索结果中；模型替身直接返回已命中的人工规则。"""
        if self._llm is not None:
            laws = [source.model_dump() for source in state.get("laws", [])]
            output = await invoke_chat(
                self._llm.with_structured_output(ContractRiskAnalysis, method="json_mode"),
                f"{CONTRACT_RISK_ANALYSIS_PROMPT}\n\n"
                f"合同条款：{state.get('extracted_terms', {})}\n"
                f"法律依据：{laws or '未检索到'}\n"
                f"风险规则：{state.get('rules', [])}\n"
                f"合同全文：{state['plain_text'][:12000]}",
            )
            sources = [
                source
                for source in state.get("laws", [])
                if source.document_id and source.knowledge_base_chunk_id and source.quoted_text
            ]
            for point in output.risk_points:
                if point.source_type == "retrieved_law":
                    by_id = {
                        (source.document_id, source.knowledge_base_chunk_id): source for source in sources
                    }
                    selected = []
                    for citation in point.citations:
                        source = by_id.get((citation.document_id, citation.knowledge_base_chunk_id))
                        if source is None:
                            raise DeepSeekInvocationError("模型引用了未召回的法律依据")
                        if source not in selected:
                            selected.append(source)
                    if not selected:
                        raise DeepSeekInvocationError("模型未提供可追溯的法律依据")
                    point.citations = selected
                    point.legal_basis = "\n".join(source.quoted_text for source in selected)
                else:
                    point.citations = []
            return {"risk_points": output.risk_points}
        return {"risk_points": [RiskPoint(**rule) for rule in state.get("rules", [])]}
