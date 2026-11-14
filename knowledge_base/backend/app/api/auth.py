"""区分管理员令牌与库级服务凭证，统一生成请求身份。"""

import asyncio
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from app.errors import AppError


class ServiceGrant(BaseModel):
    # 库访问授权需同时匹配 application_id 和 knowledge_base_ids。
    model_config = ConfigDict(extra="forbid")
    application_id: str = Field(min_length=1, max_length=128)
    knowledge_base_ids: list[str] = Field(min_length=1)
    role: str = "reader"


@dataclass(frozen=True)
class Principal:
    """管理员可跨应用访问，服务凭证按应用和库 ID 限制范围。"""

    application_id: str
    knowledge_base_ids: tuple[str, ...]
    role: str

    def can_read(self, kb):
        """检查管理员权限，或同时匹配服务凭证的应用和知识库。"""
        return self.role == "admin" or (
            self.application_id == kb.application_id and kb.id in self.knowledge_base_ids
        )

    def require_write(self):
        """校验角色是否可写。调用方仍需核对目标知识库的访问范围。"""
        if self.role not in {"admin", "writer"}:
            raise AppError(40301, "没有知识库管理权限", 403)


def parse_grants(settings):
    """在启动时校验服务密钥、角色和授权范围，返回密钥到凭证配置的映射。"""
    grants = json.loads(settings.service_keys_json)
    if not isinstance(grants, dict):
        raise ValueError("KB_SERVICE_KEYS_JSON 必须是对象")
    parsed = {}
    for key, value in grants.items():
        if not key or len(key) < 16:
            raise ValueError("服务凭证至少 16 字符")
        grant = ServiceGrant.model_validate(value)
        if grant.role not in {"reader", "writer"}:
            raise ValueError("服务凭证角色只允许 reader/writer")
        parsed[key] = grant
    return parsed


async def authenticate(request: Request, credentials: HTTPAuthorizationCredentials | None):
    """优先查找服务凭证，再验证为管理端签发的 JWT，无效凭证统一返回 40101。"""
    if credentials is None:
        raise AppError(40101, "请先登录或提供服务凭证", 401)
    token = credentials.credentials
    for key, grant in request.app.state.grants.items():
        if secrets.compare_digest(key.encode(), token.encode()):
            return Principal(grant.application_id, tuple(grant.knowledge_base_ids), grant.role)
    try:
        payload = jwt.decode(
            token,
            request.app.state.settings.jwt_secret,
            algorithms=["HS256"],
            audience="knowledge-base-admin",
            issuer="knowledge-base",
            options={"require": ["exp", "iat", "sub"]},
        )
        if payload["sub"] != request.app.state.settings.admin_username or payload.get("role") != "admin":
            raise ValueError("invalid role")
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AppError(40101, "登录已过期或凭证无效", 401) from exc
    return Principal(request.app.state.settings.admin_application_id, (), "admin")


async def login(settings, username, password):
    """校验配置中的管理员账号和 bcrypt 密码哈希，签发限时管理端令牌。"""
    valid = secrets.compare_digest(username.encode(), settings.admin_username.encode())
    try:
        checked = await asyncio.to_thread(
            bcrypt.checkpw, password.encode(), settings.admin_password_hash.encode()
        )
    except ValueError:
        checked = False
    if not valid or not checked:
        raise AppError(40101, "用户名或密码不正确", 401)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": username,
            "role": "admin",
            "iat": now,
            "exp": now + timedelta(seconds=settings.jwt_ttl_seconds),
            "aud": "knowledge-base-admin",
            "iss": "knowledge-base",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


bearer = HTTPBearer(auto_error=False)
