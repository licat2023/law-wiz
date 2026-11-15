"""为现有知识库创建关键词表，或将旧向量索引排队重建。"""

import argparse
import asyncio
import json

from sqlalchemy import or_, select
from sqlalchemy.dialects.mysql import dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from app.config import Settings
from app.documents.models import Document
from app.indexing.models import IndexRevision, KeywordLeaf, KeywordPosting
from app.indexing.service import add_job
from app.infrastructure.database import database
from app.infrastructure.models import Base
from app.knowledge_bases.models import KnowledgeBase

TABLES = (KeywordLeaf.__table__, KeywordPosting.__table__)


def mysql_schema():
    """仅输出两张新增表及其索引的 MySQL SQL，供部署前审阅。"""
    ddl = []
    for table in TABLES:
        ddl.append(str(CreateTable(table).compile(dialect=dialect())).strip())
        ddl.extend(
            str(CreateIndex(index).compile(dialect=dialect()))
            for index in sorted(table.indexes, key=lambda i: i.name)
        )
    return ";\n\n".join(ddl) + ";"


async def queue_rebuild(sessions, kb_id, limit):
    """按库排队重建当前生效的旧索引，保留仍在索引或存在失败修订的文档。"""
    pending_scope = (
        select(Document, IndexRevision)
        .join(IndexRevision, Document.active_index_id == IndexRevision.id)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.deleted_at.is_(None),
            Document.status == "ready",
            IndexRevision.status == "ready",
            IndexRevision.revision == Document.revision,
            or_(Document.desired_index_id.is_(None), Document.desired_index_id == Document.active_index_id),
            ~select(KeywordLeaf.chunk_id).where(KeywordLeaf.index_id == IndexRevision.id).exists(),
        )
    )
    async with sessions() as db:
        kb = await db.get(KnowledgeBase, kb_id)
        if kb is None or kb.deleted_at is not None:
            raise ValueError("目标知识库不存在或已删除")
        selected = list(
            (
                await db.scalars(
                    pending_scope.with_only_columns(Document.id).order_by(Document.id).limit(limit)
                )
            ).all()
        )
    jobs = []
    for document_id in selected:
        async with sessions.begin() as db:
            selected_doc = (
                await db.execute(pending_scope.where(Document.id == document_id).with_for_update())
            ).one_or_none()
            if selected_doc is not None:
                doc, index = selected_doc
                jobs.append((await add_job(db, doc, index.options)).id)
    return jobs


async def _run(args):
    settings = Settings()
    if not settings.database_url:
        raise ValueError("需要配置 KB_DATABASE_URL")
    engine, sessions = database(settings.database_url)
    try:
        if args.create_tables:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all, tables=TABLES)
            print(json.dumps({"tables": [table.name for table in TABLES]}))
        else:
            jobs = await queue_rebuild(sessions, args.knowledge_base, args.limit)
            print(json.dumps({"queued": len(jobs), "job_ids": jobs}))
    finally:
        await engine.dispose()


def main():
    """在知识库后端目录运行，用环境配置连接待升级实例。"""
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--schema-sql", action="store_true")
    action.add_argument("--create-tables", action="store_true")
    action.add_argument("--knowledge-base")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("limit 须在 1–1000")
    if args.schema_sql:
        print(mysql_schema())
    else:
        try:
            asyncio.run(_run(args))
        except ValueError as exc:
            parser.error(str(exc))


if __name__ == "__main__":
    main()
