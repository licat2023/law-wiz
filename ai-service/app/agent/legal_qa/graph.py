from langgraph.graph import END, START, StateGraph

from app.agent.legal_qa.state import LegalQaState


class LegalQaGraph:
    def __init__(self, nodes) -> None:
        graph = StateGraph(LegalQaState)
        for name in ("prepare_query", "retrieve_law", "generate_answer", "validate_citations", "finalize"):
            graph.add_node(name, getattr(nodes, name))
        graph.add_edge(START, "prepare_query")
        for left, right in zip(
            ("prepare_query", "retrieve_law", "generate_answer", "validate_citations"),
            ("retrieve_law", "generate_answer", "validate_citations", "finalize"),
            strict=True,
        ):
            graph.add_edge(left, right)
        graph.add_edge("finalize", END)
        self.workflow = graph.compile()
