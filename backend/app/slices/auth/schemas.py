"""认证切片的对外契约（Pydantic 模型）。

⚠️ **这些模型就是接口契约的唯一真源**（见 03-概要设计 §5.5）。
`/openapi.json` 由它们自动生成，Apifox 与《05-接口设计说明书》都是其下游。
**改字段名必须同步改《05》**，且属于契约变更，必须在 PR 中说明影响范围。

字段命名与 05-接口设计 §5.2 逐字一致；ID 一律为**字符串**（见 §3.4）。
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 中国大陆手机号
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

Phone = Annotated[str, Field(min_length=11, max_length=11, description="中国大陆手机号")]
Email = Annotated[str, Field(max_length=120, description="邮箱")]
Password = Annotated[str, Field(min_length=8, max_length=64, description="8–64 位，至少含字母与数字")]


def _check_password_strength(value: str) -> str:
    has_letter = any(c.isalpha() for c in value)
    has_digit = any(c.isdigit() for c in value)
    if not (has_letter and has_digit):
        raise ValueError("密码需同时包含字母与数字")
    return value


class RegisterRequest(BaseModel):
    """A-01 注册。

    `phone` 与 `email` **至少提供一个**，否则返回 40001。
    该约束由 `model_validator` 强制，与 05-接口设计 §5.2 一致。
    """

    phone: Phone | None = None
    email: Email | None = None
    password: Password
    verify_code: str = Field(min_length=4, max_length=8, description="验证码")

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, v: str | None) -> str | None:
        if v is not None and not _PHONE_RE.match(v):
            raise ValueError("手机号格式不正确")
        return v

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str | None) -> str | None:
        if v is not None and not _EMAIL_RE.match(v):
            raise ValueError("邮箱格式不正确")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return _check_password_strength(v)

    @model_validator(mode="after")
    def _require_one_identity(self) -> RegisterRequest:
        if not self.phone and not self.email:
            raise ValueError("手机号与邮箱至少提供一个")
        return self


class RegisterData(BaseModel):
    user_id: str


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=120, description="手机号或邮箱")
    password: str = Field(min_length=1, max_length=64)


class LoginData(BaseModel):
    """A-02 / A-03 的响应。

    本鉴权设计**对三端通用**（浏览器、小程序、原生 App）：访问令牌走
    `Authorization` 头、刷新令牌走请求体。不使用 `HttpOnly` Cookie，
    因为小程序与原生 App 不走浏览器 Cookie 机制（见 ADR-0010）。
    """

    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = Field(description="访问令牌有效期（秒）")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=8)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=8)


class ProfileData(BaseModel):
    real_name: str | None = None
    org_name: str | None = None
    org_role: str | None = None


class UserData(BaseModel):
    """A-05 / A-06 的响应。

    ⚠️ `phone` 与 `email` **脱敏返回**（05-接口设计 §5.2）：用户自己也不需要
    看到自己已提交的值被原文回显，而完整值一旦出现在响应里就可能被日志、截图、
    浏览器缓存带出。**完整值不通过任何接口返回。**
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    phone: str | None = None
    email: str | None = None
    account_type: str
    status: str
    last_login_at: str | None = None
    created_at: str
    profile: ProfileData | None = None


class UpdateProfileRequest(BaseModel):
    """A-06 更新资料。全部可选，仅传需要修改的字段。"""

    real_name: str | None = Field(default=None, max_length=64)
    org_name: str | None = Field(default=None, max_length=200)
    org_role: str | None = Field(default=None, max_length=64)


def mask_phone(phone: str | None) -> str | None:
    """138****0000"""
    if not phone or len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def mask_email(email: str | None) -> str | None:
    """a***@e***.com"""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if not domain:
        return email
    suffix = domain[domain.rfind(".") :] if "." in domain else ""
    return f"{local[:1]}***@{domain[:1]}***{suffix}"
