"""文件业务逻辑（M2 的文件接入部分）。

**服务层不依赖 HTTP**：接收普通参数、抛 `BusinessError`、返回普通对象。

上载校验的三道关（见 05-接口设计 §5.3）：
1. **大小** —— 读取时就设上限，避免大文件把内存撑爆；
2. **格式** —— 只看文件头魔数，不看扩展名与 `Content-Type`；
3. **重复** —— 内容寻址，同一内容只存一份（`is_duplicate`）。
"""

from __future__ import annotations

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BusinessError, ErrorCode
from app.infra.parsing import detect_format
from app.infra.storage import get_storage, object_key_for, sha256_of
from app.models.file import FileObject
from app.slices.files.schemas import FileData, UploadFileData

_settings = get_settings()


def _safe_original_name(name: str | None) -> str:
    """只保留文件名本身，去掉任何路径成分。

    文件名不参与存储路径（我们按内容哈希存），但会被展示、写日志，
    因此仍需剥掉 `../`、`C:\\` 之类的成分。
    """
    raw = (name or "").replace("\\", "/")
    base = raw.rsplit("/", 1)[-1].strip()
    return base[:255] or "未命名文件"


async def read_upload(upload: UploadFile) -> bytes:
    """读取上传内容。

    ⚠️ **最多读 `上限 + 1` 字节**，而不是把整个文件读进来再判断大小 ——
    否则一个 1 GB 的上传就能把只有 950 MiB 可用内存的服务器打垮
    （容量约束见 03-概要设计 §6.3）。多读 1 字节是为了区分"刚好等于上限"
    与"超过上限"。
    """
    limit = _settings.max_upload_bytes
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise BusinessError(
            ErrorCode.FILE_TOO_LARGE,
            f"文件超过 {limit // (1024 * 1024)} MB 上限",
        )
    return data


def save_upload(
    db: Session,
    *,
    user_id: int,
    original_name: str | None,
    data: bytes,
) -> UploadFileData:
    """校验并保存文件。返回结果与"是否重复"。"""
    if not data:
        raise BusinessError(ErrorCode.PARAM_INVALID, "文件内容为空")

    fmt = detect_format(data)
    if fmt is None:
        raise BusinessError(
            ErrorCode.UNSUPPORTED_FILE_TYPE,
            "仅支持 PDF、Word（.docx）与 JPG/PNG 图片",
        )

    digest = sha256_of(data)

    existing = db.scalar(
        select(FileObject).where(FileObject.sha256 == digest, FileObject.deleted_at.is_(None))
    )
    if existing is not None:
        # **自愈**：数据库有记录、对象存储却没有内容时把内容补回去。
        # 否则一旦两边不一致（人为清理、迁移未同步、对象存储丢数据），
        # 该内容会**永远**无法恢复 —— 因为去重路径会一直跳过写盘。
        storage = get_storage()
        if not storage.exists(existing.object_key):
            storage.put(existing.object_key, data)
        return _to_upload_data(existing, is_duplicate=True)

    storage = get_storage()
    object_key = object_key_for(digest)
    # 先落盘再写库：若写库失败，对象存储里多一个无人引用的对象，代价可忽略（内容寻址，
    # 下次同内容上传正好复用它）；反过来则会出现"库里有记录、内容却不存在"。
    storage.put(object_key, data)

    record = FileObject(
        sha256=digest,
        storage_bucket=storage.bucket,
        object_key=object_key,
        original_name=_safe_original_name(original_name),
        byte_size=len(data),
        mime_type=fmt.mime_type,
        uploader_id=user_id,
    )
    try:
        db.add(record)
        db.flush()
    except IntegrityError:
        # 并发上传同一内容：两个请求都通过了上面的查重，唯一索引拦下后者。
        # 此时应退化为"已存在"语义，而不是把 500 抛给用户。
        db.rollback()
        concurrent = db.scalar(select(FileObject).where(FileObject.sha256 == digest))
        if concurrent is None:
            raise
        return _to_upload_data(concurrent, is_duplicate=True)

    return _to_upload_data(record, is_duplicate=False)


def get_file_meta(db: Session, *, user_id: int, file_id: int) -> FileData:
    """B-02：读取文件元数据。"""
    record = db.get(FileObject, file_id)
    if record is None or record.deleted_at is not None:
        raise BusinessError(ErrorCode.FILE_NOT_FOUND, "文件不存在")
    if record.uploader_id != user_id:
        raise BusinessError(ErrorCode.FORBIDDEN, "无权访问该文件")
    return _to_file_data(record)


def _to_file_data(record: FileObject) -> FileData:
    return FileData(
        file_id=str(record.id),
        original_name=record.original_name,
        byte_size=record.byte_size,
        mime_type=record.mime_type,
        sha256=record.sha256,
    )


def _to_upload_data(record: FileObject, *, is_duplicate: bool) -> UploadFileData:
    base = _to_file_data(record)
    return UploadFileData(**base.model_dump(), is_duplicate=is_duplicate)
