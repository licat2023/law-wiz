"""请求级上下文（ContextVar）。

`request_id` 由 `RequestContextMiddleware` 在进入应用时绑定到这里，
使**任何地方**构造的 `ApiResponse` 都能自动带上它 —— 包括忘记注入
`RequestId` 依赖的路由。没有这层兜底时，漏注入的路由会返回
`request_id=""`，用户凭响应体里的号查不到任何日志，可观测性链条静默断开。

⚠️ 之所以用 `ContextVar`：`BaseHTTPMiddleware` 在 `call_next` 里以**子任务**
运行下游应用，子任务会继承绑定时的上下文，因此路由、异常处理器都能读到同一个值；
而 `request.state` 只有在拿得到 `Request` 对象的地方才可用。
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_request_id: ContextVar[str] = ContextVar("lawwiz_request_id", default="")


def bind_request_id(value: str) -> Token[str]:
    """绑定当前请求的追踪号，返回可用于还原的 token。"""
    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    """还原绑定（请求结束后调用，避免值泄漏到下一个请求）。"""
    _request_id.reset(token)


def current_request_id() -> str:
    """当前请求的追踪号；不在请求上下文内（脚本、后台任务）时返回空串。"""
    return _request_id.get()
