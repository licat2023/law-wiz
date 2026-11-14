"""文档上传、修改、下载、删除、解析和导入的 HTTP 入口。"""

import asyncio
from json import JSONDecodeError
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from app.api.deps import Db, Key, User
from app.api.responses import Envelope, ok
from app.documents import service
from app.documents.imports import import_document
from app.documents.parsing import extract_document
from app.documents.schemas import DocumentPatch, ImportRequest, MarkdownCreate
from app.errors import AppError, invalid
from app.infrastructure.idempotency import digest, idempotent
from app.knowledge_bases.service import load_kb

router = APIRouter(prefix="/api")


@router.get("/knowledge-bases/{kb_id}/documents", response_model=Envelope[dict])
async def documents(
    kb_id: str,
    request: Request,
    db: Db,
    user: User,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    query: str | None = Query(None, max_length=300),
    q: str | None = Query(None, max_length=300),
    status: str | None = None,
    format: str | None = None,
    doc_type: str | None = None,
    corpus_tier: int | None = None,
    law_name: str | None = None,
    sort: str = "-created_at",
):
    kb = await load_kb(db, user, kb_id)
    return ok(
        request,
        await service.list_documents(
            db, kb, page, page_size, query or q, status, format, doc_type, corpus_tier, law_name, sort
        ),
    )


async def file_from_form(request):
    form = await request.form(max_files=1, max_fields=5, max_part_size=65536)
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise invalid("请选择需要上传的文件")
    body = await file.read(request.app.state.settings.max_upload_bytes + 1)
    if not body or len(body) > request.app.state.settings.max_upload_bytes:
        raise invalid("文件为空或超过上传大小上限")
    filename = (getattr(file, "filename", "document") or "document").replace("\\", "/").rsplit("/", 1)[-1]
    fmt = Path(filename).suffix.lower().lstrip(".")
    if fmt not in {"docx", "pdf", "md", "markdown", "txt"}:
        raise invalid("只支持 DOCX、文本型 PDF、Markdown 和 UTF-8 TXT")
    return form, body, filename[:300], "markdown" if fmt in {"md", "markdown"} else fmt


@router.post("/knowledge-bases/{kb_id}/documents", response_model=Envelope[dict], status_code=201)
async def upload_document(kb_id: str, request: Request, db: Db, user: User, idempotency_key: Key = None):
    user.require_write()
    kb = await load_kb(db, user, kb_id)
    if request.headers.get("content-type", "").split(";", 1)[0] == "application/json":
        try:
            payload = MarkdownCreate.model_validate(await request.json())
        except JSONDecodeError as exc:
            raise invalid("文档请求不是有效 JSON") from exc
        body, title, filename, fmt, metadata = (
            payload.content.encode(),
            payload.title,
            payload.title + ".md",
            "markdown",
            payload.metadata,
        )
        content = payload.content
    else:
        form, body, filename, fmt = await file_from_form(request)
        title, metadata, content = str(form.get("title") or Path(filename).stem), {}, None
    result = await idempotent(
        db,
        user,
        f"{kb_id}:upload",
        idempotency_key,
        digest([title, filename, digest(body), metadata]),
        lambda: service.create_document(
            db, request.app.state, kb, title, filename, fmt, body, metadata, content=content
        ),
    )
    await db.commit()
    return ok(request, result)


@router.get("/knowledge-bases/{kb_id}/documents/{document_id}", response_model=Envelope[dict])
async def get_document(kb_id: str, document_id: str, request: Request, db: Db, user: User):
    kb = await load_kb(db, user, kb_id)
    doc = await service.load_document(db, kb, document_id)
    return ok(request, await service.document_view(db, doc, detail=True))


@router.patch("/knowledge-bases/{kb_id}/documents/{document_id}", response_model=Envelope[dict])
async def update_document(
    kb_id: str, document_id: str, payload: DocumentPatch, request: Request, db: Db, user: User
):
    user.require_write()
    kb = await load_kb(db, user, kb_id)
    doc = await service.load_document(db, kb, document_id)
    return ok(
        request,
        await service.change_document(
            db,
            request.app.state,
            kb,
            doc,
            payload.revision,
            title=payload.title,
            metadata=payload.metadata,
            content=payload.content,
        ),
    )


@router.put("/knowledge-bases/{kb_id}/documents/{document_id}/file", response_model=Envelope[dict])
async def replace_file(
    kb_id: str, document_id: str, request: Request, db: Db, user: User, idempotency_key: Key = None
):
    user.require_write()
    kb = await load_kb(db, user, kb_id)
    form, body, filename, fmt = await file_from_form(request)
    try:
        revision = int(str(form.get("revision")))
    except (TypeError, ValueError) as exc:
        raise invalid("替换文件需要当前文档修订号") from exc

    async def action():
        doc = await service.load_document(db, kb, document_id)
        return await service.change_document(
            db, request.app.state, kb, doc, revision, file_body=body, filename=filename, fmt=fmt
        )

    result = await idempotent(
        db,
        user,
        f"{kb_id}:{document_id}:replace",
        idempotency_key,
        digest([revision, filename, digest(body)]),
        action,
    )
    await db.commit()
    return ok(request, result)


@router.get("/knowledge-bases/{kb_id}/documents/{document_id}/file")
async def download_file(
    kb_id: str,
    document_id: str,
    request: Request,
    db: Db,
    user: User,
    revision: int | None = Query(None, ge=1),
):
    kb = await load_kb(db, user, kb_id)
    doc = await service.load_document(db, kb, document_id)
    stored = await service.revision_of(db, doc.id, revision or doc.revision)
    if stored is None or stored.file_key is None:
        raise AppError(40402, "该修订没有原文件", 404)
    path = request.app.state.settings.data_root / "files" / stored.file_key
    if not await asyncio.to_thread(path.is_file):
        raise AppError(40402, "原文件内容不可用", 404)
    return FileResponse(
        path,
        filename=stored.filename,
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/knowledge-bases/{kb_id}/documents/{document_id}", response_model=Envelope[dict])
async def remove_document(kb_id: str, document_id: str, request: Request, db: Db, user: User):
    user.require_write()
    kb = await load_kb(db, user, kb_id)
    return ok(request, await service.delete_document(db, await service.load_document(db, kb, document_id)))


@router.post("/knowledge-bases/{kb_id}/imports", response_model=Envelope[dict])
async def imports(kb_id: str, payload: ImportRequest, request: Request, db: Db, user: User):
    user.require_write()
    kb = await load_kb(db, user, kb_id)
    return ok(request, await import_document(db, request.app.state, kb, payload))


@router.post("/parsing/extract", response_model=Envelope[dict])
async def parse(request: Request, user: User):
    _, body, filename, _ = await file_from_form(request)
    # 不入知识库，不保留业务原文件；与文档任务复用同一解析封装。
    settings = request.app.state.settings
    async with request.app.state.parse_gate:
        parsed = await asyncio.to_thread(
            extract_document,
            body,
            filename,
            max_bytes=settings.max_upload_bytes,
            max_pages=settings.max_pdf_pages,
            max_chars=settings.max_text_chars,
        )
    return ok(request, {"text": parsed.text, "page_count": parsed.page_count, "format": parsed.format})
