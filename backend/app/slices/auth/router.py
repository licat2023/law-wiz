"""认证切片的 HTTP 层。

只做三件事：解析请求 → 调用服务 → 包成统一响应体。
**业务规则不写在这里。**
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import CurrentUserId, RequestId, get_db
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

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/auth/register",
    response_model=ApiResponse[RegisterData],
    status_code=status.HTTP_201_CREATED,
    summary="A-01 用户注册",
)
def register(payload: RegisterRequest, db: DbSession, rid: RequestId) -> ApiResponse[RegisterData]:
    user_id = service.register(db, payload)
    db.commit()
    return ApiResponse.ok(RegisterData(user_id=user_id), request_id=rid)


@router.post("/auth/login", response_model=ApiResponse[LoginData], summary="A-02 用户登录")
def login(payload: LoginRequest, db: DbSession, rid: RequestId) -> ApiResponse[LoginData]:
    data = service.login(db, payload)
    db.commit()
    return ApiResponse.ok(data, request_id=rid)


@router.post("/auth/refresh", response_model=ApiResponse[LoginData], summary="A-03 刷新令牌")
def refresh(payload: RefreshRequest, rid: RequestId) -> ApiResponse[LoginData]:
    return ApiResponse.ok(service.refresh(payload.refresh_token), request_id=rid)


@router.post("/auth/logout", response_model=ApiResponse[None], summary="A-04 登出")
def logout(payload: LogoutRequest, _: CurrentUserId, rid: RequestId) -> ApiResponse[None]:
    service.logout(payload.refresh_token)
    return ApiResponse.ok(None, request_id=rid)


@router.get("/users/me", response_model=ApiResponse[UserData], summary="A-05 获取当前用户信息")
def get_me(db: DbSession, user_id: CurrentUserId, rid: RequestId) -> ApiResponse[UserData]:
    return ApiResponse.ok(service.get_user_data(db, user_id), request_id=rid)


@router.put("/users/me", response_model=ApiResponse[UserData], summary="A-06 更新当前用户信息")
def update_me(
    payload: UpdateProfileRequest,
    db: DbSession,
    user_id: CurrentUserId,
    rid: RequestId,
) -> ApiResponse[UserData]:
    data = service.update_profile(db, user_id, payload)
    db.commit()
    return ApiResponse.ok(data, request_id=rid)
