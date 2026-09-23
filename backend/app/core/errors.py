"""业务错误码与统一响应体。

错误码表**逐条对应 05-接口设计 §3.3**，改动此处必须同步改文档。

设计要点：
- 错误码为 5 位整数，**按段分配**，便于一眼判断问题归属。
- HTTP 状态码与业务码**同时**返回，但**前端应以 `code` 为准**判断业务结果。
- **不返回堆栈**：`message` 面向用户，技术细节只进日志（带 request_id 关联）。
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from app.core.context import current_request_id

T = TypeVar("T")


class ErrorCode(IntEnum):
    """业务错误码。数值即 HTTP 段的语义来源，勿随意改动。"""

    OK = 0

    # --- 400xx 请求参数与格式 ---
    PARAM_INVALID = 40001
    BODY_MALFORMED = 40002
    PAGE_OUT_OF_RANGE = 40003

    # --- 401xx 未认证 ---
    ACCESS_TOKEN_INVALID = 40101
    REFRESH_TOKEN_INVALID = 40102

    # --- 403xx 已认证但无权限 ---
    FORBIDDEN = 40301

    # --- 404xx 资源不存在 ---
    # 40400 是**框架级**的"路由不存在"，用于未匹配任何路由的请求；
    # 各资源的专属码（40401~40404）表示"路由存在但资源不存在"，两者不要混用。
    RESOURCE_NOT_FOUND = 40400
    REVIEW_NOT_FOUND = 40401
    QA_SESSION_NOT_FOUND = 40402
    KB_DOC_NOT_FOUND = 40403
    FILE_NOT_FOUND = 40404

    # --- 405xx 方法不允许（框架级：路径存在但方法不匹配）---
    METHOD_NOT_ALLOWED = 40500

    # --- 409xx 业务规则冲突 ---
    PHONE_TAKEN = 40901
    EMAIL_TAKEN = 40902
    BAD_CREDENTIALS = 40903
    ACCOUNT_DISABLED = 40904
    REVIEW_IN_PROGRESS = 40905
    REVIEW_NOT_FINISHED = 40906
    REVIEW_FAILED = 40907
    KB_DOC_EXISTS = 40908
    SESSION_ARCHIVED = 40909

    # --- 413xx / 415xx ---
    FILE_TOO_LARGE = 41301
    UNSUPPORTED_FILE_TYPE = 41501

    # --- 429xx 限流 ---
    RATE_LIMITED = 42901

    # --- 500xx / 502xx / 503xx ---
    INTERNAL_ERROR = 50000
    LLM_BAD_RESPONSE = 50201
    OCR_BAD_RESPONSE = 50202
    # 数据库不可用：供健康检查使用。
    # ⚠️ 若缺此码，/health 在数据库挂掉时只能返回 `code=0`（成功）却带 HTTP 503 ——
    # 与「前端应以 code 为准」的约定直接矛盾：照约定写的前端会把 503 当成成功。
    DATABASE_UNAVAILABLE = 50300
    LLM_UNAVAILABLE = 50301
    OCR_UNAVAILABLE = 50302
    VECTOR_UNAVAILABLE = 50303


# 业务码 → HTTP 状态码。以"段"决定，避免每个码单独维护。
_HTTP_STATUS_BY_ERROR: dict[ErrorCode, int] = {
    ErrorCode.OK: 200,
    ErrorCode.PARAM_INVALID: 400,
    ErrorCode.BODY_MALFORMED: 400,
    ErrorCode.PAGE_OUT_OF_RANGE: 400,
    ErrorCode.ACCESS_TOKEN_INVALID: 401,
    ErrorCode.REFRESH_TOKEN_INVALID: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.REVIEW_NOT_FOUND: 404,
    ErrorCode.QA_SESSION_NOT_FOUND: 404,
    ErrorCode.KB_DOC_NOT_FOUND: 404,
    ErrorCode.FILE_NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.PHONE_TAKEN: 409,
    ErrorCode.EMAIL_TAKEN: 409,
    ErrorCode.BAD_CREDENTIALS: 409,
    ErrorCode.ACCOUNT_DISABLED: 409,
    ErrorCode.REVIEW_IN_PROGRESS: 409,
    ErrorCode.REVIEW_NOT_FINISHED: 409,
    ErrorCode.REVIEW_FAILED: 409,
    ErrorCode.KB_DOC_EXISTS: 409,
    ErrorCode.SESSION_ARCHIVED: 409,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_FILE_TYPE: 415,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.DATABASE_UNAVAILABLE: 503,
    ErrorCode.LLM_BAD_RESPONSE: 502,
    ErrorCode.OCR_BAD_RESPONSE: 502,
    ErrorCode.LLM_UNAVAILABLE: 503,
    ErrorCode.OCR_UNAVAILABLE: 503,
    ErrorCode.VECTOR_UNAVAILABLE: 503,
}


def http_status_for(code: ErrorCode) -> int:
    return _HTTP_STATUS_BY_ERROR.get(code, 500)


class FieldError(BaseModel):
    """字段级错误，供前端高亮具体表单项（见 05-接口设计 §3.2）。"""

    field: str
    reason: str


def _resolve_request_id(request_id: str | None) -> str:
    """未显式给号时从请求上下文取（见 core/context.py 的兜底说明）。"""
    return current_request_id() if request_id is None else request_id


class ApiResponse[T](BaseModel):
    """统一响应体。**成功与失败都是这个形状**，前端只需一处解析逻辑。"""

    code: int = 0
    message: str = "ok"
    data: T | None = None
    # 默认从请求上下文取号（见 core/context.py），因此即使某条路由忘记注入
    # `RequestId` 依赖，响应体里也**不会**出现空串；请求之外（脚本/后台）仍为空串。
    request_id: str = Field(default_factory=current_request_id)

    @classmethod
    def ok(cls, data: T | None = None, message: str = "ok", request_id: str | None = None) -> ApiResponse[T]:
        return cls(
            code=int(ErrorCode.OK),
            message=message,
            data=data,
            request_id=_resolve_request_id(request_id),
        )

    @classmethod
    def fail(
        cls,
        code: ErrorCode,
        message: str,
        data: Any = None,
        request_id: str | None = None,
    ) -> ApiResponse[T]:
        return cls(
            code=int(code),
            message=message,
            data=data,
            request_id=_resolve_request_id(request_id),
        )


class PageMeta(BaseModel):
    """分页元信息。分页响应的 data 固定为 `{items, page, page_size, total}`。"""

    page: int
    page_size: int
    total: int


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int

    @classmethod
    def of(cls, items: list[T], page: int, page_size: int, total: int) -> Page[T]:
        return cls(items=items, page=page, page_size=page_size, total=total)


class BusinessError(Exception):
    """业务异常。由全局异常处理器转成统一响应体。

    服务层只管抛，不关心 HTTP —— 这样服务层可被脚本与测试直接调用。
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        field_errors: list[FieldError] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field_errors = field_errors or []

    @property
    def http_status(self) -> int:
        return http_status_for(self.code)
