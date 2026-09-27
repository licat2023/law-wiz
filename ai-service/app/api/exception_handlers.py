from fastapi import Request
from fastapi.responses import JSONResponse

from app.agent.exceptions import AgentNotFoundError
from app.llm.deepseek import DeepSeekInvocationError


async def agent_not_found_handler(
    request: Request,
    exc: AgentNotFoundError,
) -> JSONResponse:
    """
    Agent 不存在异常的全局 HTTP 处理器。

    职责：
    - 捕获 AgentNotFoundError
    - 将领域异常转换为 HTTP 404
    - 返回统一的结构化错误响应

    不负责：
    - 查询 AgentRegistry
    - 判断 Agent 是否存在
    - 执行业务逻辑
    - 管理 requestId
    """
    del request

    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": {
                "code": "AGENT_NOT_FOUND",
                "message": f"Agent not found: {exc.agent_code}",
                "agentCode": exc.agent_code,
            },
        },
    )


async def deepseek_invocation_handler(request: Request, exc: DeepSeekInvocationError) -> JSONResponse:
    """将真实模型失败转换为稳定的服务端错误契约。"""
    del request
    return JSONResponse(
        status_code=503,
        content={"success": False, "error": {"code": "LLM_UNAVAILABLE", "message": str(exc)}},
    )
