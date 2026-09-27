from app.agent.contract_review.agent import ContractReviewAgent
from app.agent.core.base_agent import BaseAgent
from app.agent.core.demo_agent import DemoAgent
from app.agent.legal_qa.agent import LegalQaAgent
from app.core.config import settings
from app.tools.backend import FakeLawTool, FakeRiskRuleTool, LawRetrievalTool, RiskRuleTool


class AgentRegistry:
    """
    Agent 注册中心

        职责：
        1. 保存 Agent 实例
        2. 根据 agent_code 查询 Agent

        不负责：
        - 调用 Agent
        - 处理 HTTP 请求
        - 管理业务流程
        - 编写 Prompt / LLM 逻辑
    """

    def __init__(self):
        """
        初始化 Registry

        使用字典保存 Agent。

        key:
            agent_code，例如：
            demo
            contract

        value:
            对应的 Agent 实例
        """
        self._agents: dict[str, BaseAgent] = {}

        # 初始化注册当前已有的 Agent
        self.register("demo", DemoAgent())
        law_tool, risk_rule_tool = self._build_tools()
        self.register("legal_qa", LegalQaAgent(law_tool))
        self.register("contract_review", ContractReviewAgent(law_tool, risk_rule_tool))

    @staticmethod
    def _build_tools():
        """未配置服务连接时使用 Fake，保证自动化测试绝不依赖真实网络。"""
        if settings.backend_base_url and settings.backend_token:
            return LawRetrievalTool(), RiskRuleTool()
        return FakeLawTool(), FakeRiskRuleTool()

    def register(self, agent_code: str, agent: BaseAgent) -> None:
        """
        注册 Agent

        :param agent_code:
            Agent 唯一标识。
            例如:
            demo
            contract

        :param agent:
            具体 Agent 实例。

        """
        self._agents[agent_code] = agent

    def get(
        self,
        agent_code: str,
    ) -> BaseAgent | None:
        """
            根据 agent_code 获取 Agent

        :param agent_code:
            Agent标识

        :return:
            找到返回 Agent对象，
            找不到返回 None

        """
        return self._agents.get(agent_code)
