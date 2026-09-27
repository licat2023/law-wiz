"""首批核心语料包的静态完整性检查；不依赖 MySQL、向量库或网络。"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from app.models.knowledge import KbDocument, RiskRule


def test_core_corpus_has_traceable_laws_and_risk_rules() -> None:
    corpus_path = Path(__file__).parents[1] / "tools" / "core_legal_corpus.json"
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))

    assert len(payload["documents"]) >= 4
    assert all(item["corpus_tier"] == 1 and item["source_url"] for item in payload["documents"])
    assert {"中华人民共和国民法典", "中华人民共和国电子签名法"} <= {
        item["law_name"] for item in payload["documents"]
    }
    assert len(payload["risk_rules"]) >= 3
    assert all(rule["rule_code"] and rule["legal_basis"] for rule in payload["risk_rules"])


async def test_core_corpus_import_is_idempotent(db_session_factory, monkeypatch) -> None:
    """导入器必须真能落库，重复执行也不能复制法规或规则。"""
    from tools import import_core_legal_corpus as importer

    monkeypatch.setattr(importer, "SessionLocal", db_session_factory)

    await importer.main()
    await importer.main()

    async with db_session_factory() as db:
        document_count = await db.scalar(select(func.count()).select_from(KbDocument))
        rule_count = await db.scalar(select(func.count()).select_from(RiskRule))

    assert document_count == 4
    assert rule_count == 3
