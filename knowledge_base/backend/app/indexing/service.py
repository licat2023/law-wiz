"""创建索引任务并构造任务与检索块的对外表示。"""

from sqlalchemy import update

from app.documents.models import Document
from app.errors import AppError
from app.indexing.models import IndexRevision, ProcessingJob
from app.infrastructure.database import new_id


def job_view(job):
    """公开任务状态与认领次数，租约令牌留在处理器内部。"""
    return {
        key: getattr(job, key)
        for key in (
            "id",
            "document_id",
            "revision",
            "index_id",
            "status",
            "stage",
            "error_message",
            "attempts",
        )
    } | {"created_at": job.created_at.isoformat(), "updated_at": job.updated_at.isoformat()}


def chunk_view(chunk):
    """导出正文与定位字段，父块可通过 parent_id 回溯。"""
    return {
        key: getattr(chunk, key)
        for key in (
            "id",
            "parent_id",
            "level",
            "chunk_no",
            "content",
            "char_start",
            "char_end",
            "title_path",
            "page_number",
            "article_no",
            "index_id",
        )
    }


async def add_job(db, doc, options):
    """安排当前修订的目标索引和处理任务，保留生效索引供检索继续使用。"""
    index = IndexRevision(id=new_id(), document_id=doc.id, revision=doc.revision, options=options)
    # 先锁定当前修订，再插入引用文档的索引和任务。
    result = await db.execute(
        update(Document)
        .where(Document.id == doc.id, Document.revision == doc.revision, Document.deleted_at.is_(None))
        .values(desired_index_id=index.id, status="pending", error_message=None)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise AppError(40901, "文档已更新，请刷新后重试", 409)
    db.add(index)
    await db.flush()
    job = ProcessingJob(document_id=doc.id, revision=doc.revision, index_id=index.id)
    db.add(job)
    await db.flush()
    await db.refresh(doc)
    return job
