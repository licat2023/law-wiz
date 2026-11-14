"""知识库请求的会话、身份和幂等键。"""

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import Principal, authenticate, bearer
from app.errors import AppError


async def session(request: Request):
    """在请求处理成功后提交会话，将数据库约束冲突转为业务错误。"""
    async with request.app.state.sessions() as db:
        try:
            yield db
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise AppError(40901, "请求与已有操作冲突，请刷新后重试", 409) from exc


async def identity(request: Request, credentials=Depends(bearer)):
    """将 Bearer 凭证解析为管理员或受限的服务身份。"""
    return await authenticate(request, credentials)


Db = Annotated[AsyncSession, Depends(session, scope="function")]
User = Annotated[Principal, Depends(identity)]
Key = Annotated[str | None, Header(alias="Idempotency-Key", max_length=200)]
