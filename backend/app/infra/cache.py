"""Redis 客户端与刷新令牌存储。

Redis 在本项目中承担三件事（见 04-数据库设计 §4.1）：
1. **刷新令牌**（有状态、可撤销）—— 这是它存在的首要理由；
2. 令牌黑名单；
3. 接口限流计数。

⚠️ **Redis 中的数据必须可从 MySQL 重建，不作为唯一数据源。**
刷新令牌是唯一例外（它是登录态本身），因此它丢失只意味着"用户需重新登录"，
而不是"数据丢失"—— 这个取舍是有意的。
"""

from __future__ import annotations

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode

_settings = get_settings()

_redis: Redis | None = None


def get_redis() -> Redis:
    """进程内单例连接池。"""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(_settings.redis_url, decode_responses=True)
    return _redis


def _refresh_key(digest: str) -> str:
    return f"{_settings.redis_key_prefix}rt:{digest}"


def _user_refresh_set(user_id: int) -> str:
    """某用户当前有效的全部刷新令牌摘要。用于"登出所有设备"。"""
    return f"{_settings.redis_key_prefix}urt:{user_id}"


def store_refresh_token(user_id: int, token: str) -> None:
    """保存刷新令牌（存**摘要**，不存明文 —— 见 core/security.py 的说明）。"""
    from app.core.security import refresh_token_digest

    digest = refresh_token_digest(token)
    ttl = _settings.refresh_token_ttl_seconds
    try:
        pipe = get_redis().pipeline()
        # 用 set(..., ex=) 而非 setex：redis-py 已弃用 setex，而本项目的 pytest 配置
        # 会把来自 app.* 的 DeprecationWarning 升级为错误（pyproject.toml filterwarnings）
        pipe.set(_refresh_key(digest), str(user_id), ex=ttl)
        pipe.sadd(_user_refresh_set(user_id), digest)
        pipe.expire(_user_refresh_set(user_id), ttl)
        pipe.execute()
    except RedisError as exc:
        # Redis 不可用时登录失败，属服务端问题而非用户问题
        raise BusinessError(ErrorCode.INTERNAL_ERROR, "登录状态存储不可用，请稍后重试") from exc


def consume_refresh_token(token: str) -> int:
    """校验并**一次性消费**刷新令牌，返回用户 ID。

    轮换语义：刷新成功的旧令牌立即失效（见 05-接口设计 §4.2）。
    调用方拿到用户 ID 后应签发新令牌并 `store_refresh_token`。
    """
    from app.core.security import refresh_token_digest

    digest = refresh_token_digest(token)
    try:
        value = get_redis().get(_refresh_key(digest))
    except RedisError as exc:
        raise BusinessError(ErrorCode.INTERNAL_ERROR, "登录状态存储不可用，请稍后重试") from exc

    if value is None:
        raise BusinessError(ErrorCode.REFRESH_TOKEN_INVALID, "刷新令牌无效或已被撤销")

    user_id = int(value)
    revoke_refresh_token(token, user_id=user_id)
    return user_id


def revoke_refresh_token(token: str, *, user_id: int | None = None) -> None:
    """撤销单个刷新令牌。登出时调用。"""
    from app.core.security import refresh_token_digest

    digest = refresh_token_digest(token)
    try:
        pipe = get_redis().pipeline()
        pipe.delete(_refresh_key(digest))
        if user_id is not None:
            pipe.srem(_user_refresh_set(user_id), digest)
        pipe.execute()
    except RedisError:
        # 登出失败不应阻塞用户：令牌会在 TTL 到期后自然失效
        return


def revoke_all_refresh_tokens(user_id: int) -> None:
    """撤销某用户的全部刷新令牌（强制下线 / 改密码后调用）。"""
    try:
        client = get_redis()
        digests = client.smembers(_user_refresh_set(user_id))
        if digests:
            client.delete(*[_refresh_key(d) for d in digests])
        client.delete(_user_refresh_set(user_id))
    except RedisError:
        return


def ping() -> bool:
    """健康检查用。"""
    try:
        return bool(get_redis().ping())
    except RedisError:
        return False
