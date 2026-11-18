"""ContractReview LangGraph 的拓扑定义，不承载节点业务逻辑。"""

from itertools import pairwise

from langgraph.graph import END, START, StateGraph

from ai_service.review.state import ContractReviewState


class ContractReviewGraph:
    """将条款提取、法条检索和风险分析按顺序连接并编译。"""

    def __init__(self, nodes) -> None:
        graph = StateGraph(ContractReviewState)
        names = (
            "extract_terms",
            "retrieve_laws",
            "analyze_risks",
        )
        for name in names:
            graph.add_node(name, getattr(nodes, name))
        graph.add_edge(START, names[0])
        for left, right in pairwise(names):
            graph.add_edge(left, right)
        graph.add_edge(names[-1], END)
        self.workflow = graph.compile()
