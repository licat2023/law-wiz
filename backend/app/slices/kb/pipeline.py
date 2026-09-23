"""知识库索引流水线（异步）。

⚠️ 与审查流水线同样的约定：
- 执行体是**异步函数**，由 `BackgroundTasks` 在事件循环中执行；
- **分阶段提交**，使 D-03 的 `index_status` 能被轮询到；
- **本文件不实现任何 AI 能力**，只调用 `app/infra/vector.py` / `embedding.py` 的封装。

⚠️ 切分已在 D-01 完成（原因见 `schemas.py` 的说明）：`kb_document` 不存全文，
分块是全文的唯一载体。本流水线只负责**向量化**。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_beijing
from app.core.errors import BusinessError, ErrorCode
from app.infra import vector
from app.infra.concurrency import pipeline_gate
from app.infra.db.session import SessionLocal
from app.models.knowledge import KbChunk, KbDocument

logger = logging.getLogger("lawwiz.kb")

STATUS_PENDING = "pending"
STATUS_INDEXING = "indexing"
STATUS_INDEXED = "indexed"
STATUS_FAILED = "failed"


async def run_index_pipeline(document_id: int) -> None:
    """向量化入口。**异常一律转成文档的失败状态**，绝不向外抛出。"""
    async with SessionLocal() as db:
        # ⚠️ 并发闸门：必须在第一次用数据库之前取得（见 review/pipeline.py 的同处说明）
        if not await pipeline_gate.acquire():
            await _mark_failed(db, document_id, "服务繁忙，请稍后重试")
            return
        try:
            document = await db.get(KbDocument, document_id)
            if document is None:
                logger.warning("语料 %s 不存在，跳过索引", document_id)
                return

            document.index_status = STATUS_INDEXING
            await db.commit()

            chunks = (
                (
                    await db.execute(
                        select(KbChunk)
                        .where(KbChunk.kb_document_id == document_id)
                        .order_by(KbChunk.chunk_no)
                    )
                )
                .scalars()
                .all()
            )
            if not chunks:
                raise BusinessError(ErrorCode.KB_DOC_NOT_FOUND, "该语料没有可分块的内容，无法索引")

            # 只把**分块 ID 与文本**交给向量层：它不知道关系库的结构，
            # 这样更换向量实现时关系型数据无需迁移（ADR-0004）。
            # ⚠️ 向量化是 CPU 密集调用（要算全部嵌入）→ 过 `asyncio.to_thread`。
            await asyncio.to_thread(
                vector.index_document,
                document.id,
                [{"chunk_id": str(chunk.id), "text": chunk.content} for chunk in chunks],
            )

            for chunk in chunks:
                # vector_id 记录"该分块在向量库中的标识"。内存后端不返回 ID，
                # 故用 `文档:块号` 生成一个稳定标识；换成 Chroma 后由后端返回。
                chunk.vector_id = f"{document.id}:{chunk.chunk_no}"

            document.index_status = STATUS_INDEXED
            document.indexed_at = now_beijing()
            await db.commit()
            logger.info("语料 %s 索引完成，分块 %d 个", document_id, len(chunks))

        except BusinessError as exc:
            await _mark_failed(db, document_id, exc.message)
        except Exception:
            logger.exception("语料 %s 索引失败", document_id)
            await _mark_failed(db, document_id, "服务器内部错误，索引未能完成")
        finally:
            pipeline_gate.release()


async def _mark_failed(db: AsyncSession, document_id: int, message: str) -> None:
    try:
        await db.rollback()
        document = await db.get(KbDocument, document_id)
        if document is None:
            return
        document.index_status = STATUS_FAILED
        await db.commit()
        logger.warning("语料 %s 索引失败：%s", document_id, message)
    except Exception:
        logger.exception("写入语料 %s 的失败状态时又出错了", document_id)
