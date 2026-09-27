from fastapi import FastAPI

from app.agent.exceptions import AgentNotFoundError
from app.api.exception_handlers import agent_not_found_handler
from app.api.v1.agent import router

app = FastAPI(title="智法宝 AI Service")

# 注册全局异常处理器
app.add_exception_handler(
    AgentNotFoundError,
    agent_not_found_handler,
)

# 注册路由
app.include_router(router)
