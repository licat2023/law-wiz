from abc import ABC,abstractmethod

class BaseAgent(ABC):
    """
    Agent 基础抽象类

    所有具体 Agent 必须继承该类，并实现 invoke 方法。
    Runtime 只依赖 BaseAgent 契约，不关心具体 Agent 实现。
    """

    @abstractmethod
    def invoke(self,message: str,scene:str) -> dict:
        """
        执行 Agent 调用

        :param message: 用户输入消息
        :param scene: 当前业务场景
        :return: Agent 执行结果
        """

        pass
