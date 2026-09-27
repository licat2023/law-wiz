from abc import ABC, abstractmethod
from typing import Any

from app.schemas.contracts import AgentContext


class BaseAgent(ABC):
    """
    Agent 基础抽象类

    所有具体 Agent 必须继承该类，并实现 invoke 方法。
    Runtime 只依赖 BaseAgent 契约，不关心具体 Agent 实现。
    """

    @abstractmethod
    async def invoke(self, input: Any, context: AgentContext) -> Any:
        """
        执行 Agent 调用

        `input` 是具体 Agent 的输入模型；`context` 只承载通用身份与追踪信息。
        """

        raise NotImplementedError
