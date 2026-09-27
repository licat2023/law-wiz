from app.agent.core.base_agent import BaseAgent
from app.schemas.contracts import AgentContext


class DemoAgent(BaseAgent):
    async def invoke(self, input: dict, context: AgentContext) -> dict:
        message = str(input.get("message", ""))
        scene = str(input.get("scene", "CONNECTIVITY_TEST"))
        # 1.固定agent名称
        agent_name = "DemoAgent"
        # 2.根据输入message生成回复
        reply = f"收到你的消息：{message},当前场景：{scene}"
        # 3.返回字典，不依赖任何web框架对象
        return {"agent_name": agent_name, "scene": scene, "reply": reply}
