"""限流的 FastAPI 依赖（05-接口设计 §4.5）。

用法：在路由函数参数里加一个下划线参数即可：

    def login(..., _: RateLimitedAuth) -> ...:

阈值与计数主体见 `app/infra/ratelimit.py`。

**为什么用依赖而不是中间件**：限流按**接口类别**分档，而"这个接口属于哪一档"
是路由自身的属性。中间件只能靠路径去猜 —— 猜错就是限流不生效或误伤。
依赖写在路由签名里，档位一目了然，也不可能被漏掉。
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, Request, Response

from app.api.deps import CurrentUserId
from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode
from app.infra import ratelimit

RATE_LIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
RATE_LIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
RATE_LIMIT_RESET_HEADER = "X-RateLimit-Reset"
RETRY_AFTER_HEADER = "Retry-After"

_settings = get_settings()

_LIMIT_ATTR = {
    "auth": "rate_limit_auth_per_minute",
    "ai": "rate_limit_ai_per_minute",
    "read": "rate_limit_read_per_minute",
    "poll": "rate_limit_poll_per_minute",
}


def _check(category: str, subject: str, request: Request, response: Response) -> None:
    limit = getattr(_settings, _LIMIT_ATTR[category])
    allowed, remaining, reset_at = ratelimit.hit(category, subject, limit)
    _remember(request, response, limit, remaining, reset_at)
    if not allowed:
        raise BusinessError(ErrorCode.RATE_LIMITED, "请求过于频繁，请稍后重试")


def _remember(request: Request, response: Response, limit: int, remaining: int, reset_at: int) -> None:
    """同时写进 `request.state` 与响应头。

    ⚠️ 两处都要写：**异常处理器构造的是新响应**，拿不到这里设置的响应头。
    路由正常返回时用 `response.headers`，被限流时由处理器读 `request.state` 补上。
    """
    request.state.rate_limit = {"limit": limit, "remaining": remaining, "reset": reset_at}
    response.headers[RATE_LIMIT_LIMIT_HEADER] = str(limit)
    response.headers[RATE_LIMIT_REMAINING_HEADER] = str(remaining)
    response.headers[RATE_LIMIT_RESET_HEADER] = str(reset_at)


def rate_limit_headers(request: Request) -> dict[str, str]:
    """被限流时响应要带的一组头。由异常处理器调用。"""
    info = getattr(request.state, "rate_limit", None)
    if not info:
        return {}
    return {
        RETRY_AFTER_HEADER: str(max(1, info["reset"] - int(time.time()))),
        RATE_LIMIT_LIMIT_HEADER: str(info["limit"]),
        RATE_LIMIT_REMAINING_HEADER: "0",
        RATE_LIMIT_RESET_HEADER: str(info["reset"]),
    }


def _client_ip(request: Request) -> str:
    """取客户端 IP。

    ⚠️ **不直接信任 `X-Forwarded-For`**：该头可被客户端伪造，盲信等于给攻击者
    一把"换个头就绕过限流"的钥匙。此处只用 `request.client`，由部署层保证其正确 ——
    uvicorn 开 `--proxy-headers`（并配 `--forwarded-allow-ips`）后会把真实来源写进
    `request.client`。**生产部署若走 Nginx/OpenResty 反代，必须开启该选项**，
    否则所有请求会被算作同一个 IP（限流会误伤全体用户）。
    """
    return request.client.host if request.client else "unknown"


class _UserRateLimit:
    """按用户计数。依赖 `CurrentUserId`，因此这类接口必然要求登录。"""

    def __init__(self, category: str) -> None:
        self._category = category

    def __call__(self, request: Request, response: Response, user_id: CurrentUserId) -> None:
        _check(self._category, f"u{user_id}", request, response)


class _IpRateLimit:
    """按来源 IP 计数。用于认证类接口 —— 此时还没有用户身份。"""

    def __init__(self, category: str) -> None:
        self._category = category

    def __call__(self, request: Request, response: Response) -> None:
        _check(self._category, f"ip{_client_ip(request)}", request, response)


RateLimitedAuth = Annotated[None, Depends(_IpRateLimit("auth"))]
RateLimitedAI = Annotated[None, Depends(_UserRateLimit("ai"))]
RateLimitedRead = Annotated[None, Depends(_UserRateLimit("read"))]
RateLimitedPoll = Annotated[None, Depends(_UserRateLimit("poll"))]
