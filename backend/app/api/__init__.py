"""API 层公共部分。

`deps.py` 提供跨切面的横切依赖；`get_db` 从基础设施层转出，供各切片统一引用。
"""

from __future__ import annotations

from app.api.deps import (
    BearerToken,
    CurrentUserId,
    IdempotencyKey,
    RequestId,
    get_bearer_token,
    get_current_user_id,
    get_idempotency_key,
    get_request_id,
)
from app.infra.db.session import get_db

__all__ = [
    "BearerToken",
    "CurrentUserId",
    "IdempotencyKey",
    "RequestId",
    "get_bearer_token",
    "get_current_user_id",
    "get_db",
    "get_idempotency_key",
    "get_request_id",
]
