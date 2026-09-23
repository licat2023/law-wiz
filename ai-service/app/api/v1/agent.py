from fastapi import APIRouter
from app.schemas.agent import AgentTestRequest,AgentTestResponse
from app.service.agent_service import AgentService

router = APIRouter(
    prefix="/api/v1/agent",
    tags=["agent"],
)

agent_service = AgentService()

@router.post("/test",response_model=AgentTestResponse)
def test_agent(request:AgentTestRequest):

    result = agent_service.handle(
        message=request.message,
        scene=request.scene,
        agent_code = request.agent_code
    )

    return AgentTestResponse(
        request_id=request.request_id,
        success=True,
        message="Agent调用成功",
        data=result
    )