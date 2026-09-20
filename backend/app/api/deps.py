"""API 层的公共依赖。

`RequestId` 与 `CurrentUserId` 是**跨切面**的横切关注点，因此放在这里
而不是某个切片内。
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import BusinessError, ErrorCode

# 每个请求的追踪号：与响应体 request_id 及后端日志关联（05-接口设计 §3.2）
REQUEST_ID_HEADER = "X-Request-ID"

# 幂等键。必须携带该头的接口见 05-接口设计 §3.5：
# `POST /reviews`（发起审查）、`POST /qa/sessions/{id}/messages`（发消息）。
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
_IDEMPOTENCY_KEY_MAX_LENGTH = 128


def get_request_id(request: Request) -> str:
    """取请求追踪号。

    ⚠️ **必须先读 `request.state`，不能每次新建。** 本函数被调用两次：
    一次由 `RequestContextMiddleware`（结果写进响应头与访问日志），
    一次由路由的 `RequestId` 依赖（结果写进响应体）。
    若每次都生成新号，**响应头与响应体就会是两个不同的号** ——
    用户凭响应体里的号去查日志将查不到任何东西，可观测性链条断开。

    客户端传入的 `X-Request-ID` 只在长度与字符集合法时复用
    （防止超长串与不可打印字符污染日志），否则由中间件生成。
    若本函数在中间件之前被调用（例如非 HTTP 场景），退化为自行生成。
    """
    existing = getattr(request.state, "request_id", None)
    if existing:
        return str(existing)

    incoming = request.headers.get(REQUEST_ID_HEADER)
    if incoming and len(incoming) <= 64 and incoming.isascii():
        return incoming

    generated = f"req_{uuid.uuid4().hex[:16]}"
    # 回写 state：即便中间件尚未执行（或本函数被直接调用），后续调用也能取到同一个号
    request.state.request_id = generated
    return generated


RequestId = Annotated[str, Depends(get_request_id)]


# ⚠️ 必须用 HTTPBearer，**不能**用裸 `Header("authorization")`。
#
# OpenAPI 规范原文：header 参数名为 `Accept` / `Content-Type` / `Authorization`
# 时，**该参数定义 SHALL be ignored**。因此用 Header 声明时，Swagger UI 会
# 合法地忽略该输入框 —— 表现为"令牌填了却始终 401"，且难以理解。
# HTTPBearer 会注册 securityScheme，使 /docs 出现 Authorize 按钮，令牌才真正发出。
#
# `auto_error=False`：缺令牌时不由 FastAPI 返回 403，而是由本函数抛 40101，
# 保持与 05-接口设计 的错误码契约一致。
_bearer_scheme = HTTPBearer(auto_error=False)


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    """从 `Authorization: Bearer <token>` 取出访问令牌。

    ⚠️ **不使用 Cookie**：本鉴权设计对三端通用，小程序与原生 App 不走浏览器
    Cookie 机制（见 ADR-0010）。
    """
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise BusinessError(ErrorCode.ACCESS_TOKEN_INVALID, "访问令牌无效或已过期")
    return credentials.credentials.strip()


BearerToken = Annotated[str, Depends(get_bearer_token)]


def get_current_user_id(token: BearerToken) -> int:
    """解析访问令牌得到用户 ID。

    无状态：只验签名与有效期，**不查库**（05-接口设计 §4.2）。
    """
    from app.core.security import decode_access_token

    return decode_access_token(token)


CurrentUserId = Annotated[int, Depends(get_current_user_id)]


def get_idempotency_key(
    value: Annotated[str | None, Header(alias=IDEMPOTENCY_KEY_HEADER)] = None,
) -> str:
    """取幂等键。**必填** —— 缺失即 40001（05-接口设计 §3.5）。

    限制长度与字符集：该值会被写进 Redis 键，放任任意内容会污染键空间。
    """
    if value is None or not value.strip():
        raise BusinessError(ErrorCode.PARAM_INVALID, f"缺少 {IDEMPOTENCY_KEY_HEADER} 请求头")
    key = value.strip()
    if len(key) > _IDEMPOTENCY_KEY_MAX_LENGTH or not key.isascii():
        raise BusinessError(ErrorCode.PARAM_INVALID, f"{IDEMPOTENCY_KEY_HEADER} 格式不合法")
    return key


IdempotencyKey = Annotated[str, Depends(get_idempotency_key)]
