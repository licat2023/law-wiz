from app.agent.contract_review.prompts import CONTRACT_RISK_ANALYSIS_PROMPT, CONTRACT_TERM_EXTRACTION_PROMPT
from app.agent.contract_review.state import ContractReviewState
from app.llm.deepseek import invoke_chat
from app.schemas.contracts import ContractRiskAnalysis, ContractTerms, RiskPoint


class ContractReviewNodes:
    def __init__(self, law_tool, risk_rule_tool, llm=None) -> None:
        self._law_tool = law_tool
        self._risk_rule_tool = risk_rule_tool
        self._llm = llm

    async def prepare_contract(self, state: ContractReviewState) -> ContractReviewState:
        return state

    async def extract_terms(self, state: ContractReviewState) -> ContractReviewState:
        if self._llm is not None:
            output = await invoke_chat(self._llm.with_structured_output(ContractTerms),
                f"{CONTRACT_TERM_EXTRACTION_PROMPT}\n\n合同全文：\n{state['plain_text'][:12000]}"
            )
            return {"extracted_terms": output.model_dump()}
        return {"extracted_terms": {"text_length": len(state["plain_text"])}}

    async def retrieve_laws(self, state: ContractReviewState) -> ContractReviewState:
        context = state["context"]
        return {
            "laws": await self._law_tool.search(
                state["plain_text"][:200], request_id=context.request_id, trace_id=context.trace_id
            )
        }

    async def retrieve_risk_rules(self, state: ContractReviewState) -> ContractReviewState:
        context = state["context"]
        return {
            "rules": await self._risk_rule_tool.match(
                state["plain_text"], request_id=context.request_id, trace_id=context.trace_id
            )
        }

    async def analyze_risks(self, state: ContractReviewState) -> ContractReviewState:
        if self._llm is not None:
            laws = "\n".join(source.quoted_text or "" for source in state.get("laws", []))
            output = await invoke_chat(self._llm.with_structured_output(ContractRiskAnalysis),
                f"{CONTRACT_RISK_ANALYSIS_PROMPT}\n\n"
                f"合同条款：{state.get('extracted_terms', {})}\n"
                f"法律依据：{laws or '未检索到'}\n"
                f"风险规则：{state.get('rules', [])}\n"
                f"合同全文：{state['plain_text'][:12000]}"
            )
            return {"risk_points": output.risk_points}
        return {"risk_points": [RiskPoint(**rule) for rule in state.get("rules", [])]}

    async def validate_sources(self, state: ContractReviewState) -> ContractReviewState:
        return state

    async def finalize(self, state: ContractReviewState) -> ContractReviewState:
        return state
