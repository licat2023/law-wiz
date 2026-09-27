from fastapi import APIRouter

from app.schemas.agent import AgentTestRequest, AgentTestResponse
from app.schemas.contracts import AgentContext, AgentInvokeRequest, AgentInvokeResponse
from app.service.agent_service import AgentService

router = APIRouter(
    prefix="/api/v1/agent",
    tags=["agent"],
)

agent_service = AgentService()


@router.post("/test", response_model=AgentTestResponse)
async def test_agent(request: AgentTestRequest):

    result = await agent_service.handle(
        agent_code=request.agent_code,
        input={"message": request.message, "scene": request.scene},
        context=AgentContext(requestId=request.request_id),
    )
    data = result.model_dump() if hasattr(result, "model_dump") else result
    return AgentTestResponse(
        request_id=request.request_id, success=True, message="Agent调用成功", data=data
    )


@router.post("/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(request: AgentInvokeRequest) -> AgentInvokeResponse:
    """Backend 的受控调用入口；只理解 Agent API 契约，不暴露 Graph 细节。"""
    result = await agent_service.handle(request.agent_code, request.input, request.context)
    data = result.model_dump() if hasattr(result, "model_dump") else result
    return AgentInvokeResponse(requestId=request.context.request_id, data=data)
