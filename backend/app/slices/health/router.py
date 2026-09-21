"""健康检查（F-01）。

对应 05-接口设计 §5.7。

**三条约定**：
1. 任一非关键组件异常时 `status = degraded` 且 HTTP 仍返回 **200 + code 0**；
2. **仅当数据库不可用时返回 503** —— 数据库不可用意味着服务实质不可用；
3. ⚠️ 返回 503 时**必须是失败响应体**（`code = 50300`），不能是 `code = 0`。

第 3 条的由来：本接口起初在 503 时仍用 `ApiResponse.ok()`，于是出现
「HTTP 503 但 `code: 0 / message: "ok"`」的自相矛盾。按 05-接口设计 §3.2
的约定「**前端应以 `code` 为准**判断业务结果」，照约定写的前端会把 503 当成成功。
根因是错误码表里当时没有"数据库不可用"这一项，只得用 `ok()` 兜底 ——
现已补上 `DATABASE_UNAVAILABLE = 50300`，两者一致。

本接口**不返回任何凭据、连接串或内部地址**。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import RequestId, get_db
from app.core.clock import now_beijing, to_iso
from app.core.config import get_settings
from app.core.errors import ApiResponse, ErrorCode
from app.infra.cache import ping as redis_ping
from app.preflight import describe_runtime

logger = logging.getLogger("lawwiz.health")

router = APIRouter(tags=["系统"])

_settings = get_settings()
# ⚠️ 时间必须经 core.clock 序列化：契约要求 ISO 8601 带时区偏移（05-接口设计 §3）
_STARTED_AT = to_iso(now_beijing())

DbSession = Annotated[Session, Depends(get_db)]

# 逐条列出的失败响应，使 503 出现在 OpenAPI 里（FastAPI 默认只写 200）
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ApiResponse[dict[str, Any]],
        "description": "数据库不可用，服务实质不可用（`code = 50300`）",
    }
}


def _check_database(db: Session) -> str:
    """探测数据库。

    ⚠️ **异常必须记日志。** 若静默吞掉异常，`/health` 只回报
    "database: unavailable" 而控制台毫无线索 —— 排障只能靠猜。
    日志记录异常类型与消息（不记完整堆栈，避免连接类错误刷屏），
    排查具体原因时再用 `db_echo=true` 或直连数据库。
    """
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning(
            "数据库健康检查失败：%s: %s",
            type(exc).__name__,
            str(exc)[:300],
        )
        return "unavailable"


def _check_capability(name: str, provider: str) -> str:
    """外部能力的配置状态。

    一期多数能力是 `stub`（未接入真实服务），此时报 `not_configured` 而不是
    `unavailable` —— 两者含义不同：前者是"还没接"，后者是"接了但坏了"，
    混为一谈会让运维误判。
    """
    if provider == "stub":
        return "not_configured"
    return "ok"


@router.get(
    "/health",
    response_model=ApiResponse[dict[str, Any]],
    summary="F-01 健康检查",
    responses=_ERROR_RESPONSES,
)
def health(db: DbSession, rid: RequestId, response: Response) -> ApiResponse[dict[str, Any]]:
    db_status = _check_database(db)
    redis_status = "ok" if redis_ping() else "unavailable"

    components: dict[str, str] = {
        "database": db_status,
        "redis": redis_status,
        "vector_store": _check_capability("vector_store", _settings.vector_backend),
        "llm_provider": _check_capability("llm_provider", _settings.llm_provider),
        "ocr_provider": _check_capability("ocr_provider", _settings.ocr_provider),
    }

    payload: dict[str, Any] = {
        "status": "ok",
        "version": "0.1.0",
        "runtime": {
            **describe_runtime(),
            "started_at": _STARTED_AT,
        },
        "components": components,
        "checked_at": to_iso(now_beijing()),
    }

    # 仅数据库不可用视为整体不可用
    if db_status != "ok":
        payload["status"] = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        # ⚠️ 必须是失败响应体：HTTP 503 配 code 0 会让"以 code 为准"的前端误判为成功
        return ApiResponse.fail(
            ErrorCode.DATABASE_UNAVAILABLE,
            "数据库不可用，服务暂时无法处理请求",
            data=payload,
            request_id=rid,
        )

    if any(v == "unavailable" for v in components.values()):
        payload["status"] = "degraded"

    return ApiResponse.ok(payload, request_id=rid)
