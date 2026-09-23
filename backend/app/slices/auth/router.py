"""认证切片的 HTTP 层。

只做三件事：解析请求 → 调用服务 → 包成统一响应体。
**业务规则不写在这里。**
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import CurrentUserId, RateLimitedAuth, RateLimitedRead, RequestId, get_db
from app.core.errors import ApiResponse
from app.slices.auth import service
from app.slices.auth.schemas import (
    LoginData,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterData,
    RegisterRequest,
    UpdateProfileRequest,
    UserData,
)

router = APIRouter(tags=["认证与用户"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "/auth/register",
    response_model=ApiResponse[RegisterData],
    status_code=status.HTTP_201_CREATED,
    summary="A-01 用户注册",
)
async def register(
    payload: RegisterRequest, db: DbSession, rid: RequestId, _rate: RateLimitedAuth
) -> ApiResponse[RegisterData]:
    user_id = await service.register(db, payload)
    await db.commit()
    return ApiResponse.ok(RegisterData(user_id=user_id), request_id=rid)


@router.post("/auth/login", response_model=ApiResponse[LoginData], summary="A-02 用户登录")
async def login(
    payload: LoginRequest, db: DbSession, rid: RequestId, _rate: RateLimitedAuth
) -> ApiResponse[LoginData]:
    data = await service.login(db, payload)
    await db.commit()
    return ApiResponse.ok(data, request_id=rid)


@router.post("/auth/refresh", response_model=ApiResponse[LoginData], summary="A-03 刷新令牌")
async def refresh(payload: RefreshRequest, rid: RequestId, _rate: RateLimitedAuth) -> ApiResponse[LoginData]:
    return ApiResponse.ok(await service.refresh(payload.refresh_token), request_id=rid)


@router.post("/auth/logout", response_model=ApiResponse[None], summary="A-04 登出")
async def logout(
    payload: LogoutRequest, _user: CurrentUserId, rid: RequestId, _rate: RateLimitedRead
) -> ApiResponse[None]:
    await service.logout(payload.refresh_token)
    return ApiResponse.ok(None, request_id=rid)


@router.get("/users/me", response_model=ApiResponse[UserData], summary="A-05 获取当前用户信息")
async def get_me(
    db: DbSession, user_id: CurrentUserId, rid: RequestId, _rate: RateLimitedRead
) -> ApiResponse[UserData]:
    return ApiResponse.ok(await service.get_user_data(db, user_id), request_id=rid)


@router.put("/users/me", response_model=ApiResponse[UserData], summary="A-06 更新当前用户信息")
async def update_me(
    payload: UpdateProfileRequest,
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
    _rate: RateLimitedRead,
) -> ApiResponse[UserData]:
    data = await service.update_profile(db, user_id, payload)
    await db.commit()
    return ApiResponse.ok(data, request_id=rid)
