"""知识库列表、创建、更新和删除的 HTTP 入口。"""

from fastapi import APIRouter, Query, Request

from app.api.deps import Db, User
from app.api.responses import Envelope, ok
from app.knowledge_bases import service
from app.knowledge_bases.schemas import KnowledgeBaseCreate, KnowledgeBasePatch

router = APIRouter(prefix="/api")


@router.get("/knowledge-bases", response_model=Envelope[dict])
async def kbs(
    request: Request, db: Db, user: User, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)
):
    # 列表仅包含当前身份可访问且未删除的知识库。
    return ok(request, await service.list_kbs(db, user, page, page_size))


@router.post("/knowledge-bases", response_model=Envelope[dict], status_code=201)
async def create_kb(payload: KnowledgeBaseCreate, request: Request, db: Db, user: User):
    # 仅管理员可创建库，可指定归属应用。
    return ok(request, await service.create_kb(db, user, payload))


@router.get("/knowledge-bases/{kb_id}", response_model=Envelope[dict])
async def get_kb(kb_id: str, request: Request, db: Db, user: User):
    # 返回库设置及未删除文档的计数。
    return ok(request, await service.kb_view(db, await service.load_kb(db, user, kb_id)))


@router.patch("/knowledge-bases/{kb_id}", response_model=Envelope[dict])
async def update_kb(kb_id: str, payload: KnowledgeBasePatch, request: Request, db: Db, user: User):
    # 合并库的默认切分选项，已有索引继续使用各自的配置快照。
    user.require_write()
    kb = await service.load_kb(db, user, kb_id)
    return ok(request, await service.patch_kb(db, kb, payload))


@router.delete("/knowledge-bases/{kb_id}", response_model=Envelope[dict])
async def delete_kb(kb_id: str, request: Request, db: Db, user: User):
    # 隐藏本库并软删除当前文档，由文档删除流程登记关联清理。
    user.require_write()
    kb = await service.load_kb(db, user, kb_id)
    await service.delete_kb(db, kb)
    return ok(request, {"id": kb.id})
