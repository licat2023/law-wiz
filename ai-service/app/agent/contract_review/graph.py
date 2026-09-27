"""ContractReview LangGraph 的拓扑定义，不承载节点业务逻辑。"""

from itertools import pairwise

from langgraph.graph import END, START, StateGraph

from app.agent.contract_review.state import ContractReviewState


class ContractReviewGraph:
    def __init__(self, nodes) -> None:
        graph = StateGraph(ContractReviewState)
        names = (
            "prepare_contract",
            "extract_terms",
            "retrieve_laws",
            "retrieve_risk_rules",
            "analyze_risks",
            "validate_sources",
            "finalize",
        )
        for name in names:
            graph.add_node(name, getattr(nodes, name))
        graph.add_edge(START, names[0])
        for left, right in pairwise(names):
            graph.add_edge(left, right)
        graph.add_edge(names[-1], END)
        self.workflow = graph.compile()
