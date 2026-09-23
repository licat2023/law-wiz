from app.agent.registry import AgentRegistry
from app.agent.runtime import AgentRuntime

class AgentService:
    """
      Agent业务服务层。

      职责：
      - 接收上层调用参数
      - 调用AgentRuntime执行Agent

      不负责：
      - 查找Agent
      - 创建具体Agent
      - 管理Agent生命周期
      """
    def __init__(self):
        """
        初始化Agent服务。

        创建Registry，并注入Runtime。

        Service只持有Runtime，
        不直接接触具体Agent。
        """

        # 创建Agent注册中心
        registry = AgentRegistry()

        # Runtime负责Agent调度
        self.runtime = AgentRuntime(
            registry
        )



    def handle(
        self,
        message: str,
        scene: str,
        agent_code: str = "demo"
    ) -> dict:
        """
        调用Agent。

        :param message:
            用户输入

        :param scene:
            当前业务场景

        :param agent_code:
            指定执行的Agent。
            默认demo，保持旧接口兼容。

        """

        return self.runtime.invoke(
            agent_code,
            message,
            scene
        )