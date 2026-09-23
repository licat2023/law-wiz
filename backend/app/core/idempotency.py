"""接口幂等：以 `Idempotency-Key` 请求头去重（05-接口设计 §3.5）。

契约：**同一 key 在 24 小时内重复提交，返回首次的结果，而不重复创建。**

存储用 Redis（已有依赖），键带 `lawwiz:` 前缀，与其它键空间隔离。

⚠️ 键带**接口作用域**（`idem:<scope>:<key>`）：客户端完全可能在两个接口上
用同一个 key（例如复用了同一个 UUID）。若不隔离，后一个接口会原样返回
**前一个接口的响应体**，形状不符时前端拿到的是无法解析的数据
（响应模型校验失败 → 50000），而这类错误极难定位到"客户端复用了 key"。

⚠️ **已知的窄竞态**：本实现是"先查、再执行、后写"，两个**同时**到达的同 key
请求理论上都可能查不到缓存而各执行一次。这里不做更复杂的抢占（SETNX + 等待），
理由是业务侧已有第二道防线 —— `POST /reviews` 对同一文件默认拒绝并发
（`40905`），双击按钮不会产生两个任务。若将来放松那道校验，此处必须同步加固。

⚠️ Redis 不可用时**降级为不缓存**而不是报错：幂等是优化，不该让功能整体不可用。
"""

from __future__ import annotations

import json
import logging

from redis.exceptions import RedisError

from app.infra.cache import get_redis

logger = logging.getLogger("lawwiz.idempotency")

_KEY_PREFIX = "idem:"
_TTL_SECONDS = 24 * 3600


def _key(scope: str, key: str) -> str:
    from app.core.config import get_settings

    return f"{get_settings().redis_key_prefix}{_KEY_PREFIX}{scope}:{key}"


async def load(scope: str, key: str) -> dict | None:
    """取该接口上首次请求的响应体。没有则返回 None。"""
    try:
        cached = await get_redis().get(_key(scope, key))
    except RedisError as exc:
        logger.warning("幂等缓存读取失败，按未命中处理：%s", exc)
        return None
    if cached is None:
        return None
    try:
        payload = json.loads(cached)
    except json.JSONDecodeError:
        logger.warning("幂等缓存内容损坏，按未命中处理")
        return None
    return payload if isinstance(payload, dict) else None


async def save(scope: str, key: str, payload: dict) -> None:
    """记录首次请求的响应体，供重复提交时原样返回。"""
    try:
        await get_redis().set(_key(scope, key), json.dumps(payload, ensure_ascii=False), ex=_TTL_SECONDS)
    except RedisError as exc:
        logger.warning("幂等缓存写入失败（不影响本次请求）：%s", exc)
