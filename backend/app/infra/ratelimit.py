"""限流计数器（05-接口设计 §4.5）。

四个类别与阈值来自文档：

| 类别 | 阈值 | 计数主体 | 目的 |
| --- | --- | --- | --- |
| `auth` | 10 / 分 | **IP** | 防暴力破解、防批量注册 |
| `ai` | 10 / 分 | 用户 | 保护 LLM 额度（真实调用是花钱的） |
| `read` | 120 / 分 | 用户 | 查询类兜底 |
| `poll` | 60 / 分 | 用户 | 轮询任务状态 |

**算法：固定窗口计数器（Redis INCR + EXPIRE）。** 选它的理由是语义简单、
一次往返完成；代价是窗口边界处允许突发（最坏约 2 倍）。若将来要求更严格，
再换滑动窗口 —— 但不要在没有明确需求时就上滑动窗口。

⚠️ **Redis 不可用时放行**并在日志告警（与幂等缓存同一取舍）：限流是保护措施，
不该让服务整体不可用。代价是 Redis 故障期间限流失效 —— 这一点必须知情。
"""

from __future__ import annotations

import logging
import time

from redis.exceptions import RedisError

from app.infra.cache import get_redis

logger = logging.getLogger("lawwiz.ratelimit")

WINDOW_SECONDS = 60


def _incr(key: str, ttl: int) -> int | None:
    """计数 +1 并返回新值；Redis 不可用时返回 None（调用方放行）。

    **测试替换此函数**即可用内存字典代替 Redis —— 与 `core/idempotency.py`
    同一手法：只替换存储，阈值判断逻辑仍走真实实现。
    """
    try:
        pipe = get_redis().pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        count, _ = pipe.execute()
        return int(count)
    except RedisError as exc:
        logger.warning("限流计数失败，本次放行：%s", exc)
        return None


def hit(category: str, subject: str, limit: int) -> tuple[bool, int, int]:
    """记录一次请求。

    返回 `(是否放行, 剩余次数, 窗口重置的 Unix 时间戳)`。
    """
    from app.core.config import get_settings

    now = int(time.time())
    window = now // WINDOW_SECONDS
    reset_at = (window + 1) * WINDOW_SECONDS

    key = f"{get_settings().redis_key_prefix}rl:{category}:{subject}:{window}"
    # TTL 略大于窗口：确保键能在窗口结束后自然消失，不依赖清理任务
    count = _incr(key, WINDOW_SECONDS + 5)
    if count is None:
        return True, limit, reset_at

    remaining = max(0, limit - count)
    return count <= limit, remaining, reset_at
