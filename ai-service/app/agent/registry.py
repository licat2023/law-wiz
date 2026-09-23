from app.agent.core.base_agent import BaseAgent
from app.agent.core.demo_agent import DemoAgent

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
        self._agents:dict [str,BaseAgent] = {}

        #初始化注册当前已有的 Agent
        self.register(
            "demo",
            DemoAgent()
        )

    def register(
            self,
            agent_code: str,
            agent: BaseAgent
    )->None:
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
    )->BaseAgent | None:
        """
            根据 agent_code 获取 Agent

        :param agent_code:
            Agent标识

        :return:
            找到返回 Agent对象，
            找不到返回 None

        """
        return self._agents.get(agent_code)
