"""全局异常处理器。

**目标：任何失败都返回统一响应体，且不泄露内部细节。**
FastAPI 默认的 422 响应体形状与我们的信封不同，必须在此改写 ——
否则前端要写两套解析逻辑，这与 05-接口设计 §2 的原则 3 冲突。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.ratelimit import rate_limit_headers
from app.core.errors import ApiResponse, BusinessError, ErrorCode, FieldError, http_status_for

logger = logging.getLogger("lawwiz.error")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def _business_error(request: Request, exc: BusinessError) -> JSONResponse:
        """业务异常。服务层只管抛，这里负责翻译成 HTTP。"""
        data = {"details": [e.model_dump() for e in exc.field_errors]} if exc.field_errors else None
        # 被限流时必须补上 Retry-After 与 X-RateLimit-* —— 限流依赖设置的头
        # 在**新构造的响应**里会丢失，所以从 request.state 取回来（见 api/ratelimit.py）
        headers = rate_limit_headers(request) if exc.code == ErrorCode.RATE_LIMITED else None
        return JSONResponse(
            status_code=exc.http_status,
            content=ApiResponse.fail(
                exc.code, exc.message, data=data, request_id=_request_id(request)
            ).model_dump(),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """把 FastAPI 的校验错误转成我们的字段级错误格式。

        `loc` 形如 `("body", "phone")`，需剥掉首段的来源标记只留字段名，
        否则前端拿到的 field 是 `body.phone`，无法与表单字段对应。
        """
        # ⚠️ **JSON 解析失败必须与字段校验失败区分开**：契约里它们是两个码
        # （05-接口设计 §3.3：40002 请求体格式错误 / 40001 参数校验失败）。
        # FastAPI 会把 `json.JSONDecodeError` 也包成 RequestValidationError，
        # 若不在此分流，畸形的请求体会被当成"字段格式不正确"，误导前端。
        if any(err.get("type") == "json_invalid" for err in exc.errors()):
            return JSONResponse(
                status_code=http_status_for(ErrorCode.BODY_MALFORMED),
                content=ApiResponse.fail(
                    ErrorCode.BODY_MALFORMED,
                    "请求体格式错误",
                    request_id=_request_id(request),
                ).model_dump(),
            )

        field_errors: list[FieldError] = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            field = ".".join(loc) or "(unknown)"
            field_errors.append(FieldError(field=field, reason=err.get("msg", "格式不正确")))

        return JSONResponse(
            status_code=http_status_for(ErrorCode.PARAM_INVALID),
            content=ApiResponse.fail(
                ErrorCode.PARAM_INVALID,
                "请求参数校验失败",
                data={"details": [e.model_dump() for e in field_errors]},
                request_id=_request_id(request),
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """框架级 HTTP 异常（404 路由不存在、405 方法不允许等）。

        ⚠️ 映射必须保持"**码段与 HTTP 状态一致**"：
        - 未匹配路由 = 40400（资源不存在），**不能**复用 `40401`（那是"审查任务不存在"，
          会让前端在任务列表页显示"任务不存在"）；
        - 方法不匹配 = 40500，**不能**落到 `50000` —— 前端按 code 判断时会把
          用错方法的请求显示成"服务器内部错误"，掩盖真实原因。
        """
        mapped = {
            401: ErrorCode.ACCESS_TOKEN_INVALID,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.RESOURCE_NOT_FOUND,
            405: ErrorCode.METHOD_NOT_ALLOWED,
            429: ErrorCode.RATE_LIMITED,
        }.get(exc.status_code)

        if mapped is None:
            logger.warning(
                "未映射的框架级 HTTP 异常：status=%s detail=%s request_id=%s",
                exc.status_code,
                exc.detail,
                _request_id(request),
            )
            mapped = ErrorCode.INTERNAL_ERROR

        # message 面向用户展示，统一给中文；不透传框架的英文 detail
        message = {
            ErrorCode.ACCESS_TOKEN_INVALID: "访问令牌无效或已过期",
            ErrorCode.FORBIDDEN: "无权访问该资源",
            ErrorCode.RESOURCE_NOT_FOUND: "请求的资源不存在",
            ErrorCode.METHOD_NOT_ALLOWED: "请求方法不被允许",
            ErrorCode.RATE_LIMITED: "请求过于频繁，请稍后重试",
            ErrorCode.INTERNAL_ERROR: "服务器内部错误",
        }[mapped]
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.fail(mapped, message, request_id=_request_id(request)).model_dump(),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """兜底。

        ⚠️ **堆栈只进日志，绝不进响应体。** 响应体只给一个可对日志的 request_id。
        """
        logger.exception("未处理异常 request_id=%s", _request_id(request))
        return JSONResponse(
            status_code=http_status_for(ErrorCode.INTERNAL_ERROR),
            content=ApiResponse.fail(
                ErrorCode.INTERNAL_ERROR,
                "服务器内部错误",
                request_id=_request_id(request),
            ).model_dump(),
        )
