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
    model_config = ConfigDict(extra="forbid")
    application_id: str = Field(min_length=1, max_length=128)
    knowledge_base_ids: list[str] = Field(min_length=1)
    role: str = "reader"


@dataclass(frozen=True)
class Principal:
    application_id: str
    knowledge_base_ids: tuple[str, ...]
    role: str

    def can_read(self, kb):
        return self.role == "admin" or (
            self.application_id == kb.application_id and kb.id in self.knowledge_base_ids
        )

    def require_write(self):
        if self.role not in {"admin", "writer"}:
            raise AppError(40301, "没有知识库管理权限", 403)


def parse_grants(settings):
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
