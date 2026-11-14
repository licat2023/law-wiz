"""知识库检索 HTTP 入口。"""

from fastapi import APIRouter, Request

from app.api.deps import Db, User
from app.api.responses import Envelope, ok
from app.knowledge_bases.service import load_kb
from app.retrieval.schemas import SearchRequest
from app.retrieval.service import search

router = APIRouter(prefix="/api")


@router.post("/knowledge-bases/{kb_id}/search", response_model=Envelope[dict])
async def retrieve(kb_id: str, payload: SearchRequest, request: Request, db: Db, user: User):
    kb = await load_kb(db, user, kb_id)
    return ok(request, await search(db, request.app.state, kb, payload))
