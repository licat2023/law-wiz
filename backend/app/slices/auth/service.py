"""认证业务逻辑（M1）。

**服务层不依赖 HTTP**：只接收普通参数、抛 `BusinessError`、返回普通对象。
这样它可以被脚本、后台任务与测试直接调用，不必构造请求上下文。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_beijing, to_iso
from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode, FieldError
from app.core.security import (
    create_access_token,
    hash_password,
    new_refresh_token,
    verify_password,
)
from app.infra.cache import (
    consume_refresh_token,
    revoke_refresh_token,
    store_refresh_token,
)
from app.models.user import User, UserProfile
from app.slices.auth.schemas import (
    LoginData,
    LoginRequest,
    ProfileData,
    RegisterRequest,
    UpdateProfileRequest,
    UserData,
    mask_email,
    mask_phone,
)

_settings = get_settings()

# 开发环境固定验证码（05-接口设计 §8）。生产环境由启动校验强制关闭。
_DEV_FIXED_CODE = "000000"


def _verify_code_ok(code: str) -> bool:
    """验证码校验。

    ⚠️ 一期**没有接短信/邮件通道**（无法自建，见 02-技术栈 §3.6）。因此：
    - `development` / `testing` 环境接受固定验证码；
    - `production` 环境**固定验证码被禁用**，此时本函数一律返回 False ——
      意味着生产环境必须接入真实通道后才能注册。这是一处**有意的未完成**，
      写在这里以免被误认为遗漏。
    """
    if _settings.is_production:
        return False
    return code == _DEV_FIXED_CODE


async def register(db: AsyncSession, payload: RegisterRequest) -> str:
    """注册。返回 user_id（字符串，见 05-接口设计 §3.4）。"""
    if not _verify_code_ok(payload.verify_code):
        raise BusinessError(
            ErrorCode.PARAM_INVALID,
            "验证码不正确",
            field_errors=[FieldError(field="verify_code", reason="验证码不正确")],
        )

    # 唯一性先在应用层查一次，给出**字段级**错误；数据库唯一索引仍是最终防线
    if payload.phone:
        exists = await db.scalar(select(User.id).where(User.phone == payload.phone))
        if exists:
            raise BusinessError(
                ErrorCode.PHONE_TAKEN,
                "该手机号已被注册",
                field_errors=[FieldError(field="phone", reason="该手机号已被注册")],
            )
    if payload.email:
        exists = await db.scalar(select(User.id).where(User.email == payload.email))
        if exists:
            raise BusinessError(
                ErrorCode.EMAIL_TAKEN,
                "该邮箱已被注册",
                field_errors=[FieldError(field="email", reason="该邮箱已被注册")],
            )

    user = User(
        phone=payload.phone,
        email=payload.email,
        password_hash=await hash_password(payload.password),
    )
    db.add(user)
    await db.flush()
    # 资料行随之建立，使 A-06 更新时不需再判"是否存在"
    db.add(UserProfile(user_id=user.id))
    await db.flush()
    return str(user.id)


async def login(db: AsyncSession, payload: LoginRequest) -> LoginData:
    """登录。

    ⚠️ **失败时一律返回 40903，不区分"账号不存在"与"密码错误"**（05-接口设计 §5.2）：
    区分这两者等于给攻击者一个枚举已注册账号的接口。
    """
    account = payload.account.strip()
    user = await db.scalar(select(User).where((User.phone == account) | (User.email == account)))

    if user is None or not await verify_password(payload.password, user.password_hash):
        raise BusinessError(ErrorCode.BAD_CREDENTIALS, "账号或密码错误")

    if user.status != "active":
        raise BusinessError(ErrorCode.ACCOUNT_DISABLED, "账号已被停用")

    user.last_login_at = now_beijing()
    await db.flush()
    return await _issue_tokens(user.id)


async def refresh(payload_token: str) -> LoginData:
    """刷新令牌。

    轮换语义：`consume_refresh_token` 一次性消费旧令牌，随后签发新的
    —— 旧令牌被盗用后的可用窗口因此缩短，异常刷新也可被检测（05-接口设计 §4.2）。
    """
    user_id = await consume_refresh_token(payload_token)
    return await _issue_tokens(user_id)


async def logout(payload_token: str) -> None:
    await revoke_refresh_token(payload_token)


async def _issue_tokens(user_id: int) -> LoginData:
    access_token, expires_in = create_access_token(user_id)
    refresh_token = new_refresh_token()
    await store_refresh_token(user_id, refresh_token)
    return LoginData(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


async def get_user_data(db: AsyncSession, user_id: int) -> UserData:
    """当前用户信息。手机号与邮箱脱敏后返回。"""
    user = await db.get(User, user_id)
    if user is None:
        raise BusinessError(ErrorCode.ACCESS_TOKEN_INVALID, "访问令牌无效或已过期")

    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    return UserData(
        id=str(user.id),
        phone=mask_phone(user.phone),
        email=mask_email(user.email),
        account_type=user.account_type,
        status=user.status,
        last_login_at=to_iso(user.last_login_at),
        created_at=to_iso(user.created_at) or "",
        profile=(
            ProfileData(
                real_name=profile.real_name,
                org_name=profile.org_name,
                org_role=profile.org_role,
            )
            if profile
            else None
        ),
    )


async def update_profile(db: AsyncSession, user_id: int, payload: UpdateProfileRequest) -> UserData:
    """更新资料。仅写入请求中显式给出的字段（`None` 表示"不改"）。"""
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)

    for field in ("real_name", "org_name", "org_role"):
        value = getattr(payload, field)
        if value is not None:
            setattr(profile, field, value)

    await db.flush()
    return await get_user_data(db, user_id)
