"""请求追踪中间件。

每个请求分配 `request_id`，写入：
1. `request.state.request_id` —— 供路由与异常处理器读取，放进响应体；
2. 响应头 `X-Request-ID` —— 便于用户报障时直接提供；
3. 访问日志 —— 使"用户说某次请求失败"能被定位到具体日志行。

没有这个机制时，多用户并发下的错误日志无法归属到具体请求。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger("lawwiz.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = get_request_id(request)
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "%s %s -> 未捕获异常 (%.0fms) request_id=%s",
                request.method,
                request.url.path,
                elapsed_ms,
                request_id,
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        # 慢请求单独记，便于对照 01-需求说明书 §4.1 的性能指标
        level = logging.WARNING if elapsed_ms > 3000 else logging.INFO
        logger.log(
            level,
            "%s %s -> %d (%.0fms) request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response
