"""密码哈希与令牌。

关于密码哈希库的选择：**直接用 `bcrypt`，不用 `passlib`**。
`passlib` 已长期停止维护，且其 bcrypt 后端会读取 `bcrypt.__about__`，
在新版 bcrypt 上会抛异常（`AttributeError: module 'bcrypt' has no attribute '__about__'`）。
直接用 bcrypt 的 API 更短、更可控，也少一个依赖。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import secrets
import uuid
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

_settings = get_settings()

BCRYPT_ROUNDS = 12
# bcrypt 只处理前 72 字节，超长密码需先截断，否则新版 bcrypt 会直接报错
_BCRYPT_MAX_BYTES = 72


def _hash_password_blocking(plain: str) -> str:
    raw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def _verify_password_blocking(plain: str, password_hash: str) -> bool:
    try:
        raw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except ValueError, TypeError:
        return False


async def hash_password(plain: str) -> str:
    """生成密码哈希。**绝不存明文**（04-数据库设计 §7.1）。

    ⚠️ 异步不是装饰：bcrypt 12 轮约 **100–300 ms** 的纯 CPU 时间，
    直接在事件循环里跑会让期间**所有**请求排队（登录、上传都会卡）。
    交给 `asyncio.to_thread` 走线程池。
    """
    return await asyncio.to_thread(_hash_password_blocking, plain)


async def verify_password(plain: str, password_hash: str) -> bool:
    """校验密码。哈希串损坏时返回 False 而不是抛异常，避免泄露内部状态。

    与 `hash_password` 同理：bcrypt 校验同样是百毫秒级 CPU 操作。
    """
    return await asyncio.to_thread(_verify_password_blocking, plain, password_hash)


# ============================================================
# 访问令牌（JWT，短时效、无状态）
# ============================================================


def create_access_token(user_id: int, *, now: dt.datetime | None = None) -> tuple[str, int]:
    """签发访问令牌。返回 (token, expires_in_seconds)。

    无状态：校验只验签名与有效期，**不查库**（见 05-接口设计 §4.2）。
    """
    issued_at = now or dt.datetime.now(dt.UTC)
    expires_in = _settings.access_token_ttl_seconds
    payload: dict[str, Any] = {
        "sub": str(user_id),  # 04/05 约定：ID 以字符串传递
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + dt.timedelta(seconds=expires_in)).timestamp()),
        "typ": "access",
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> int:
    """校验访问令牌并返回用户 ID。

    失败一律抛 BusinessError(ACCESS_TOKEN_INVALID)，**不区分过期/签名错误/格式错误** ——
    对外区分这些细节没有收益，只会给攻击者提供信息。
    """
    from app.core.errors import BusinessError, ErrorCode  # 局部导入避免循环依赖

    try:
        payload = jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise BusinessError(ErrorCode.ACCESS_TOKEN_INVALID, "访问令牌无效或已过期") from exc

    if payload.get("typ") != "access":
        raise BusinessError(ErrorCode.ACCESS_TOKEN_INVALID, "访问令牌无效或已过期")

    subject = payload.get("sub")
    if not subject or not str(subject).isdigit():
        raise BusinessError(ErrorCode.ACCESS_TOKEN_INVALID, "访问令牌无效或已过期")
    return int(subject)


# ============================================================
# 刷新令牌（随机串，有状态，存 Redis，可撤销）
# ============================================================


def new_refresh_token() -> str:
    """生成刷新令牌明文。

    ⚠️ **入库（Redis）的是它的 SHA-256 摘要，不是明文。**
    这样即使 Redis 被读取，也无法直接拿去换访问令牌 —— 与"绝不存明文密码"
    是同一个道理。校验时对来串求摘要再比对。
    """
    return "rt_" + secrets.token_urlsafe(48)


def refresh_token_digest(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
