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
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import REQUEST_ID_HEADER, get_request_id
from app.core.config import get_settings
from app.core.errors import ApiResponse, ErrorCode, http_status_for

logger = logging.getLogger("lawwiz.access")

# JSON 请求体的上限。最大的合法请求是 kb 语料（上限 50 万字符，
# 中文 UTF-8 约 1.5 MB）加上包装与本层余量，4 MB 足够宽裕。
_MAX_JSON_BODY_BYTES = 4 * 1024 * 1024

# 文件上传走 multipart，大小由 LAWWIZ_MAX_UPLOAD_BYTES 判定；
# 这里额外留出 multipart 边界与表单头的开销。
_MULTIPART_OVERHEAD_BYTES = 2 * 1024 * 1024


def _body_limit(content_type: str) -> int:
    if content_type.lower().startswith("multipart/form-data"):
        return get_settings().max_upload_bytes + _MULTIPART_OVERHEAD_BYTES
    return _MAX_JSON_BODY_BYTES


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """限制请求体大小。

    ⚠️ **为什么必须有这一层**：Pydantic 的 `max_length` 是**在请求体被完整解析之后**
    才生效的 —— 一个 500 MB 的 JSON 会先把内存吃掉，然后才轮到字段校验说"太长了"。
    仅有字段级上限等于没有防线。

    实现依据是 `Content-Length` 头（浏览器与 axios 发 JSON 时都会带）。
    **局限**：使用 chunked 传输编码、不带 `Content-Length` 的请求不受此层约束 ——
    那需要流式计数，属于部署层（反代）更适合承担的职责。
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        raw = request.headers.get("content-length")
        if raw is not None and raw.isdigit():
            limit = _body_limit(request.headers.get("content-type", ""))
            if int(raw) > limit:
                logger.warning(
                    "请求体过大被拒：%s 字节 > %s 字节  %s %s request_id=%s",
                    raw,
                    limit,
                    request.method,
                    request.url.path,
                    get_request_id(request),
                )
                # 复用 FILE_TOO_LARGE（41301 → HTTP 413 Payload Too Large）：
                # 契约里没有单独的"请求体过大"错误码，而 413 的语义正好吻合。
                # 注意：本层在异常处理器**之外**，因此必须直接构造响应体。
                return JSONResponse(
                    status_code=http_status_for(ErrorCode.FILE_TOO_LARGE),
                    content=ApiResponse.fail(
                        ErrorCode.FILE_TOO_LARGE,
                        "请求体超过大小上限",
                        request_id=get_request_id(request),
                    ).model_dump(),
                )
        return await call_next(request)


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
