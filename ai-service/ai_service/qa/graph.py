"""组装 Agent 工作流。"""

from itertools import pairwise

from langgraph.graph import END, START, StateGraph

from ai_service.qa.state import LegalQaState


class LegalQaGraph:
    """按检索、生成回答和复核引用顺序编译节点。"""

    def __init__(self, nodes) -> None:
        graph = StateGraph(LegalQaState)
        names = ("retrieve_law", "generate_answer", "validate_citations")
        for name in names:
            graph.add_node(name, getattr(nodes, name))
        graph.add_edge(START, names[0])
        for left, right in pairwise(names):
            graph.add_edge(left, right)
        graph.add_edge(names[-1], END)
        self.workflow = graph.compile()
