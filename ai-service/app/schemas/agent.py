from pydantic import BaseModel,ConfigDict,Field

class AgentTestRequest(BaseModel):
    """
     Agent测试请求。

     populate_by_name=True：
     既允许使用Python字段名，例如 agent_code，
     也允许使用alias，例如 agentCode。
     """
    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(alias = "requestId")
    # 默认使用demo，保证旧请求没有agentCode时仍然可以正常运行
    agent_code: str = Field(
        default="demo",
        alias="agentCode"
    )
    message: str
    scene: str

class AgentTestResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(alias="requestId")
    success: bool
    message: str
    data: dict
