"""数据库租约驱动的单处理器；发布必须匹配最新目标修订与租约。"""

import asyncio
import contextlib
import logging
from datetime import timedelta

from sqlalchemy import delete, or_, select, update

from app.documents.models import Document, DocumentRevision
from app.documents.parsing import TextBlock, extract_document
from app.documents.service import revision_of
from app.errors import AppError
from app.indexing.chunking import ChunkOptions, semantic_units, split_document
from app.indexing.models import Chunk, IndexRevision, ProcessingJob
from app.infrastructure.database import new_id, now

logger = logging.getLogger("knowledge_base.jobs")


class LeaseLost(Exception):
    pass


class Processor:
    def __init__(self, state):
        self.state = state
        self.lock = asyncio.Lock()

    async def loop(self):
        while True:
            try:
                worked = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("知识库处理器暂不可用，等待下次重试")
                worked = False
            if not worked:
                await asyncio.sleep(self.state.settings.worker_poll_seconds)

    async def claim(self):
        async with self.state.sessions() as db:
            job = await db.scalar(
                select(ProcessingJob)
                .where(
                    or_(
                        ProcessingJob.status == "pending",
                        (ProcessingJob.status == "processing") & (ProcessingJob.lease_until < now()),
                    )
                )
                .order_by(ProcessingJob.created_at)
                .limit(1)
            )
            if job is None:
                return None
            if job.attempts >= self.state.settings.max_attempts:
                job.status = "failed"
                job.error_message = "任务恢复次数已达上限，请手动重试"
                index = await db.get(IndexRevision, job.index_id)
                doc = await db.get(Document, job.document_id)
                if index and job.stage != "cleanup":
                    index.status = "failed"
                if doc and doc.deleted_at is None and doc.desired_index_id == job.index_id:
                    doc.status = "failed"
                    doc.error_message = job.error_message
                await db.commit()
                return None
            token = new_id()
            conditions = [ProcessingJob.id == job.id, ProcessingJob.status == job.status]
            if job.status == "processing":
                conditions.append(ProcessingJob.lease_token == job.lease_token)
            result = await db.execute(
                update(ProcessingJob)
                .where(*conditions)
                .values(
                    status="processing",
                    attempts=job.attempts + 1,
                    lease_token=token,
                    lease_until=now() + timedelta(seconds=self.state.settings.lease_seconds),
                )
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            return (job.id, token) if result.rowcount == 1 else None

    async def run_once(self):
        async with self.lock:
            claim = await self.claim()
            if claim is None:
                return False
            job_id, token = claim
            heartbeat = asyncio.create_task(self._heartbeat(job_id, token))
            try:
                await self.process(job_id, token)
            except LeaseLost:
                pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                message = (
                    exc.message if isinstance(exc, AppError) else "文档处理失败，请检查文件与服务配置后重试"
                )
                await self.fail(job_id, token, message)
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            return True

    async def _heartbeat(self, job_id, token):
        while True:
            await asyncio.sleep(self.state.settings.lease_seconds / 3)
            async with self.state.sessions() as db:
                await db.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.lease_token == token,
                        ProcessingJob.status == "processing",
                    )
                    .values(lease_until=now() + timedelta(seconds=self.state.settings.lease_seconds))
                )
                await db.commit()

    async def check(self, db, job_id, token):
        job = await db.get(ProcessingJob, job_id, populate_existing=True)
        if (
            job is None
            or job.lease_token != token
            or job.status != "processing"
            or job.lease_until is None
            or job.lease_until < now()
        ):
            raise LeaseLost()
        doc = await db.get(Document, job.document_id, populate_existing=True)
        if doc is None:
            raise LeaseLost()
        if job.stage != "cleanup" and (
            doc.deleted_at is not None or doc.revision != job.revision or doc.desired_index_id != job.index_id
        ):
            job.status, job.stage = "cancelled", "cancelled"
            await db.commit()
            raise LeaseLost()
        return job, doc

    async def stage(self, job_id, token, stage):
        async with self.state.sessions() as db:
            job, doc = await self.check(db, job_id, token)
            job.stage = stage
            doc.status = stage
            await db.commit()

    async def process(self, job_id, token):
        async with self.state.sessions() as db:
            job, doc = await self.check(db, job_id, token)
            document_id, revision_number, index_id, kb_id = (
                doc.id,
                job.revision,
                job.index_id,
                doc.knowledge_base_id,
            )
            if job.stage == "cleanup":
                await asyncio.to_thread(self.state.vector.delete_document, document_id)
                revisions = (
                    await db.scalars(
                        select(DocumentRevision).where(DocumentRevision.document_id == document_id)
                    )
                ).all()
                for revision in revisions:
                    if revision.file_key:
                        await asyncio.to_thread(
                            (self.state.settings.data_root / "files" / revision.file_key).unlink,
                            missing_ok=True,
                        )
                job.status = "succeeded"
                await db.commit()
                return
            index = await db.get(IndexRevision, index_id)
            options = ChunkOptions.model_validate(index.options)
            revision = await revision_of(db, document_id, revision_number)
            text, blocks_data, metadata = revision.content, revision.blocks, revision.source_metadata
            file_key, filename = revision.file_key, revision.filename
        await self.stage(job_id, token, "parsing")
        if text is None:
            body = await asyncio.to_thread((self.state.settings.data_root / "files" / file_key).read_bytes)
            parsed = await asyncio.to_thread(
                extract_document,
                body,
                filename,
                max_bytes=self.state.settings.max_upload_bytes,
                max_pages=self.state.settings.max_pdf_pages,
                max_chars=self.state.settings.max_text_chars,
            )
            text, blocks_data = parsed.text, parsed.block_data()
            async with self.state.sessions() as db:
                await self.check(db, job_id, token)
                revision = await revision_of(db, document_id, revision_number)
                revision.content, revision.blocks, revision.page_count = text, blocks_data, parsed.page_count
                await db.commit()
        await self.stage(job_id, token, "chunking")
        vectors = None
        if options.chunking_strategy == "semantic":
            units = await asyncio.to_thread(
                semantic_units, text, options.chunk_size, max_units=self.state.settings.max_chunks
            )
            if len(units) > self.state.settings.max_chunks:
                raise AppError(40001, "语义候选块过多，请增大分块长度")
            vectors = await self.state.embedding.embed([text[a:b] for a, b in units])
        chunks = await asyncio.to_thread(
            split_document,
            text,
            options,
            [TextBlock(**b) for b in blocks_data or []],
            semantic_vectors=vectors,
            max_chunks=self.state.settings.max_chunks,
            legal=metadata.get("document_profile") == "legal_article"
            or metadata.get("doc_type") in ("law", "interpretation", "legal_article"),
            article_no=metadata.get("article_no"),
        )
        if not chunks or len(chunks) > self.state.settings.max_chunks:
            raise AppError(40001, "分块为空或超过数量上限，请调整文档和切分设置")
        await self.stage(job_id, token, "embedding")
        leaves = [chunk for chunk in chunks if chunk.is_leaf]
        embeddings = await self.state.embedding.embed([chunk.content for chunk in leaves])
        identifiers = {chunk.key: new_id() for chunk in chunks}
        fingerprint = self.state.embedding.fingerprint
        # 每次重试覆盖该版本的全部旧向量与块；旧生效版本位于不同 index_id。
        await asyncio.to_thread(self.state.vector.delete_index, fingerprint, index_id)
        await asyncio.to_thread(
            self.state.vector.upsert,
            fingerprint,
            kb_id,
            document_id,
            index_id,
            [identifiers[c.key] for c in leaves],
            [c.content for c in leaves],
            embeddings,
        )
        async with self.state.sessions() as db:
            job, doc = await self.check(db, job_id, token)
            await db.execute(delete(Chunk).where(Chunk.index_id == index_id))
            for chunk in chunks:
                db.add(
                    Chunk(
                        id=identifiers[chunk.key],
                        index_id=index_id,
                        parent_id=identifiers.get(chunk.parent_key),
                        level=chunk.level,
                        chunk_no=chunk.chunk_no,
                        content=chunk.content,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                        title_path=chunk.title_path[:2000],
                        page_number=chunk.page_number,
                        article_no=chunk.article_no,
                        is_leaf=chunk.is_leaf,
                    )
                )
            await db.flush()
            published = await db.execute(
                update(Document)
                .where(
                    Document.id == document_id,
                    Document.revision == revision_number,
                    Document.desired_index_id == index_id,
                    Document.deleted_at.is_(None),
                    select(ProcessingJob.id)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.lease_token == token,
                        ProcessingJob.status == "processing",
                        ProcessingJob.lease_until >= now(),
                    )
                    .exists(),
                )
                .values(active_index_id=index_id, chunk_count=len(leaves), status="ready", error_message=None)
                .execution_options(synchronize_session=False)
            )
            if published.rowcount != 1:
                await db.rollback()
                raise LeaseLost()
            index = await db.get(IndexRevision, index_id)
            index.status, index.fingerprint = "ready", fingerprint
            job.status, job.stage = "succeeded", "ready"
            job.lease_until, job.lease_token = None, None
            await db.commit()

    async def fail(self, job_id, token, message):
        async with self.state.sessions() as db:
            job = await db.get(ProcessingJob, job_id)
            if job is None or job.lease_token != token or job.status != "processing":
                return
            retry = job.stage == "cleanup" and job.attempts < self.state.settings.max_attempts
            job.status, job.error_message = ("pending" if retry else "failed"), message
            job.lease_until, job.lease_token = None, None
            index = await db.get(IndexRevision, job.index_id)
            doc = await db.get(Document, job.document_id)
            if job.stage != "cleanup":
                index.status, index.error_message = "failed", message
            if doc and doc.deleted_at is None and doc.desired_index_id == job.index_id:
                doc.status, doc.error_message = "failed", message
            await db.commit()
