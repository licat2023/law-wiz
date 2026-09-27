"""可重复导入首批核心法规与人工风险规则；不联网、不包含任何凭据。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.errors import BusinessError, ErrorCode
from app.infra.db.session import SessionLocal
from app.models.knowledge import RiskRule
from app.slices.kb import service
from app.slices.kb.schemas import CreateDocumentRequest

CORPUS_FILE = Path(__file__).with_name("core_legal_corpus.json")


async def main() -> None:
    payload = json.loads(CORPUS_FILE.read_text(encoding="utf-8"))
    async with SessionLocal() as db:
        for document in payload["documents"]:
            try:
                await service.create_document(db, CreateDocumentRequest.model_validate(document))
            except BusinessError as exc:
                # 内容哈希重复时可安全跳过，使脚本可重复执行；其他错误仍抛出。
                if exc.code != ErrorCode.KB_DOC_EXISTS:
                    raise
            await db.commit()
        for rule in payload["risk_rules"]:
            existing = await db.scalar(select(RiskRule.id).where(RiskRule.rule_code == rule["rule_code"]))
            if existing is None:
                db.add(RiskRule(**rule))
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
