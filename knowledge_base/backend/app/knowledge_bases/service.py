"""知识库设置、访问范围和库级删除。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import Principal
from app.api.responses import page
from app.documents.models import Document
from app.documents.service import delete_document
from app.errors import AppError, invalid
from app.indexing.chunking import ChunkOptions
from app.infrastructure.database import now
from app.knowledge_bases.models import KnowledgeBase


async def load_kb(db: AsyncSession, principal: Principal, kb_id: str):
    """读取可访问的活动库。缺失、删除和越权统一返回 40401。"""
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None or kb.deleted_at is not None or not principal.can_read(kb):
        raise AppError(40401, "知识库不存在或无权访问", 404)
    return kb


async def kb_view(db, kb):
    """返回库概要和当前未删除的文档数量。"""
    count = await db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.knowledge_base_id == kb.id, Document.deleted_at.is_(None))
    )
    return {
        "id": kb.id,
        "application_id": kb.application_id,
        "name": kb.name,
        "description": kb.description,
        **kb.options,
        "document_count": count,
        "created_at": kb.created_at.isoformat(),
        "updated_at": kb.updated_at.isoformat(),
    }


async def list_kbs(db, principal, page_number, page_size):
    """分页列出可见知识库，服务凭证同时受应用归属和库授权列表限制。"""
    conditions = [KnowledgeBase.deleted_at.is_(None)]
    if principal.role != "admin":
        conditions += [
            KnowledgeBase.application_id == principal.application_id,
            KnowledgeBase.id.in_(principal.knowledge_base_ids),
        ]
    total = await db.scalar(select(func.count()).select_from(KnowledgeBase).where(*conditions))
    kbs = (
        await db.scalars(
            select(KnowledgeBase)
            .where(*conditions)
            .order_by(KnowledgeBase.created_at.desc())
            .offset((page_number - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return page([await kb_view(db, kb) for kb in kbs], total, page_number, page_size)


async def create_kb(db, principal, payload):
    """由管理员创建库，未指定应用时使用其默认应用。"""
    if principal.role != "admin":
        raise AppError(40301, "创建知识库需要管理员身份", 403)
    kb = KnowledgeBase(
        application_id=payload.application_id or principal.application_id,
        name=payload.name,
        description=payload.description,
        options=ChunkOptions.model_validate(payload.model_dump()).model_dump(),
    )
    db.add(kb)
    await db.flush()
    return await kb_view(db, kb)


async def patch_kb(db, kb, payload):
    """合并并校验库的默认设置，已安排的索引任务保留原有选项。"""
    values = payload.model_dump(exclude_unset=True, exclude_none=True)
    options = ChunkOptions.model_validate(
        kb.options | {k: v for k, v in values.items() if k in ChunkOptions.model_fields}
    )
    kb.options = options.model_dump()
    if "name" in values:
        if not values["name"].strip():
            raise invalid("名称不能为空")
        kb.name = values["name"].strip()
    if "description" in values:
        kb.description = values["description"]
    await db.flush()
    return await kb_view(db, kb)


async def delete_kb(db, kb):
    """Hide the knowledge base and queue cleanup for its current documents."""
    kb.deleted_at = now()
    documents = (
        await db.scalars(
            select(Document).where(Document.knowledge_base_id == kb.id, Document.deleted_at.is_(None))
        )
    ).all()
    for document in documents:
        await delete_document(db, document)
