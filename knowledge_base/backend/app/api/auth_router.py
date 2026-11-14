"""知识库管理端登录入口。"""

from fastapi import APIRouter, Request

from app.api.auth import login
from app.api.auth_schemas import Login
from app.api.responses import Envelope, ok

router = APIRouter(prefix="/api")


@router.post("/auth/login", response_model=Envelope[dict])
async def sign_in(payload: Login, request: Request):
    # 配置中的唯一管理员可凭账号密码换取限时 Bearer 令牌。
    return ok(request, await login(request.app.state.settings, payload.username, payload.password))
