"""知识库索引流水线（异步）。

⚠️ 与审查流水线同样的约定：
- 执行体是**同步函数**，由 `BackgroundTasks` 放进线程池，避免阻塞事件循环；
- **分阶段提交**，使 D-03 的 `index_status` 能被轮询到；
- **本文件不实现任何 AI 能力**，只调用 `app/infra/vector.py` / `embedding.py` 的封装。

⚠️ 切分已在 D-01 完成（原因见 `schemas.py` 的说明）：`kb_document` 不存全文，
分块是全文的唯一载体。本流水线只负责**向量化**。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_beijing
from app.core.errors import BusinessError, ErrorCode
from app.infra import vector
from app.infra.db.session import SessionLocal
from app.models.knowledge import KbChunk, KbDocument

logger = logging.getLogger("lawwiz.kb")

STATUS_PENDING = "pending"
STATUS_INDEXING = "indexing"
STATUS_INDEXED = "indexed"
STATUS_FAILED = "failed"


def run_index_pipeline(document_id: int) -> None:
    """向量化入口。**异常一律转成文档的失败状态**，绝不向外抛出。"""
    db = SessionLocal()
    try:
        document = db.get(KbDocument, document_id)
        if document is None:
            logger.warning("语料 %s 不存在，跳过索引", document_id)
            return

        document.index_status = STATUS_INDEXING
        db.commit()

        chunks = db.scalars(
            select(KbChunk).where(KbChunk.kb_document_id == document_id).order_by(KbChunk.chunk_no)
        ).all()
        if not chunks:
            raise BusinessError(ErrorCode.KB_DOC_NOT_FOUND, "该语料没有可分块的内容，无法索引")

        # 只把**分块 ID 与文本**交给向量层：它不知道关系库的结构，
        # 这样更换向量实现时关系型数据无需迁移（ADR-0004）。
        vector.index_document(
            document.id,
            [{"chunk_id": str(chunk.id), "text": chunk.content} for chunk in chunks],
        )

        for chunk in chunks:
            # vector_id 记录"该分块在向量库中的标识"。内存后端不返回 ID，
            # 故用 `文档:块号` 生成一个稳定标识；换成 Chroma 后由后端返回。
            chunk.vector_id = f"{document.id}:{chunk.chunk_no}"

        document.index_status = STATUS_INDEXED
        document.indexed_at = now_beijing()
        db.commit()
        logger.info("语料 %s 索引完成，分块 %d 个", document_id, len(chunks))

    except BusinessError as exc:
        _mark_failed(db, document_id, exc.message)
    except Exception:
        logger.exception("语料 %s 索引失败", document_id)
        _mark_failed(db, document_id, "服务器内部错误，索引未能完成")
    finally:
        db.close()


def _mark_failed(db: Session, document_id: int, message: str) -> None:
    try:
        db.rollback()
        document = db.get(KbDocument, document_id)
        if document is None:
            return
        document.index_status = STATUS_FAILED
        db.commit()
        logger.warning("语料 %s 索引失败：%s", document_id, message)
    except Exception:
        logger.exception("写入语料 %s 的失败状态时又出错了", document_id)
