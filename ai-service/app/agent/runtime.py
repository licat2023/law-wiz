from app.agent.registry import AgentRegistry

class AgentRuntime:
    """
     Agent Runtime 运行时核心。

        职责：
        1. 接收调用请求
        2. 根据 agent_code 查找对应 Agent
        3. 调用 Agent 的 invoke 方法

        不负责：
        - HTTP请求处理
        - Agent注册
        - Prompt编写
        - LLM调用
        - 业务逻辑
    """
    def __init__(
            self,
            registry: AgentRegistry
    ):
        """
        初始化 Runtime。

        Runtime 不自己创建 Registry，
        而是由外部传入。

        这种设计叫：
        依赖注入（Dependency Injection）

        好处：
        Runtime 不关心 Registry 怎么创建，
        只依赖它提供的能力。:
        """
        self.registry = registry

    def invoke(self,agent_code: str,message: str,scene: str) -> dict:
        """
               调用指定 Agent。
               流程：
               agent_code
                   |
                   v
               registry.get()
                   |
                   v
               Agent.invoke()

               :param agent_code:
                   Agent唯一标识，例如 demo

               :param message:
                   用户输入

               :param scene:
                   当前业务场景

               :return:
                   Agent执行结果

               :raises ValueError:
                   Agent不存在
        """
        #根据agent_code查找Agent
        agent = self.registry.get(agent_code)

        # 如果没有找到对应 Agent Runtime只表达领域错误：
        # "这个Agent不存在"  不应该转换成HTTP状态码 因为Runtime不知道HTTP
        if agent is None:
            raise ValueError( f"Agent not found: {agent_code}")

        # 调用具体Agent
        # Runtime只知道 BaseAgent 定义的 invoke 契约
        # 不关心具体是谁实现的
        return agent.invoke(
            message,
            scene
        )
