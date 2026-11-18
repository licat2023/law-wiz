"""两个法律 Agent 使用的请求追踪上下文。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentContext:
    """将请求追踪号传给检索工具。"""

    request_id: str
    trace_id: str | None = None
