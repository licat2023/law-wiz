from app.agent.contract_review.state import ContractReviewState
from app.schemas.contracts import RiskPoint


class ContractReviewNodes:
    def __init__(self, law_tool, risk_rule_tool) -> None:
        self._law_tool = law_tool
        self._risk_rule_tool = risk_rule_tool

    async def prepare_contract(self, state: ContractReviewState) -> ContractReviewState:
        return state

    async def extract_terms(self, state: ContractReviewState) -> ContractReviewState:
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
        return {"risk_points": [RiskPoint(**rule) for rule in state.get("rules", [])]}

    async def validate_sources(self, state: ContractReviewState) -> ContractReviewState:
        return state

    async def finalize(self, state: ContractReviewState) -> ContractReviewState:
        return state
