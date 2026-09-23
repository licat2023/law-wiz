"""ORM 模型层面的约定（方言相关，普通接口测试覆盖不到）。

⚠️ 这里放的是**换数据库方言才会暴露**的缺陷：SQLite 支持 `INSERT ... RETURNING`，
MySQL 不支持 —— 只跑 SQLite 的用例看不出差别。实测教训：C-01 发起审查在 MySQL 上
返回 50000（`MissingGreenlet`），而当时 143 个用例全绿。
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401  确保全部模型已注册到 metadata
from app.infra.db.base import Base
from app.models.knowledge import KbDocument

_TIMESTAMP_COLUMNS = ("created_at", "updated_at", "generated_at")

# 04-数据库设计 明确定义、且**只有复合/非外键列**因而不会被外键自动索引覆盖的索引。
# 名字与模型 `__table_args__` 里声明的一致；少一个就说明有人从模型里删掉了它 ——
# 那会让 `create_all` 出来的测试库没有该索引，而迁移库有，两边形状不再一致。
_EXPECTED_INDEXES = {
    ("contract", "idx_contract_owner_status"),
    ("kb_chunk", "idx_kb_chunk_vector"),
    ("kb_document", "idx_kb_document_article"),
    ("kb_document", "idx_kb_document_status"),
    ("kb_document", "idx_kb_document_type_tier"),
    ("qa_message", "idx_qa_message_session"),
    ("qa_session", "idx_qa_session_user"),
    ("review_task", "idx_review_task_user_status"),
    ("risk_point", "idx_risk_point_task_level"),
    ("risk_rule", "idx_risk_rule_active"),
}


def test_timestamp_columns_have_python_side_values() -> None:
    """时间戳列必须有 Python 侧取值，不能只依赖 `server_default`。

    MySQL 不支持 `INSERT ... RETURNING`：插入后 SQLAlchemy 不知道服务端写了什么，
    会把列标记为过期；异步会话里读它（例如放进响应体）会触发隐式 SELECT，
    而那次 IO 发生在 greenlet 之外 → `MissingGreenlet`。
    """
    checked = 0
    for table in Base.metadata.tables.values():
        for name in _TIMESTAMP_COLUMNS:
            column = table.columns.get(name)
            if column is None:
                continue
            checked += 1
            assert column.default is not None, (
                f"{table.name}.{name} 缺少 Python 侧默认值："
                "MySQL 上读取它会触发隐式 IO，异步会话将抛 MissingGreenlet"
            )
            if name == "updated_at":
                assert column.onupdate is not None, (
                    f"{table.name}.updated_at 缺少 onupdate：更新时不会刷新（docs/04 §2.3 要求）"
                )
    assert checked >= 15, f"应覆盖全部时间戳列，实际只检查到 {checked} 个（模型是否漏注册？）"


def test_documented_indexes_are_declared_on_the_models() -> None:
    """docs/04 定义的索引必须在**模型**里，不能只写在迁移脚本里。

    迁移脚本只影响真实数据库；而测试库是 `create_all` 从模型建的 ——
    模型漏声明时，测试库与生产库的形状就悄悄分叉了。
    """
    declared = {
        (table.name, index.name) for table in Base.metadata.tables.values() for index in table.indexes
    }
    missing = _EXPECTED_INDEXES - declared
    assert not missing, f"模型缺少这些索引：{sorted(missing)}"


def test_kb_document_hash_length_check_is_enforced(engine) -> None:
    """`content_hash` 必须是 64 位十六进制 —— 由 CHECK 约束兜底（docs/04 §4.5）。

    契约层面这个值由应用生成，但 CHECK 是防"绕过应用写库"的最后一道：
    它不止是 DDL 里的一行字，本用例确认它**真的会拒绝**非法值。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _insert(hash_value: str) -> None:
        async with factory() as db:
            db.add(
                KbDocument(
                    doc_type="law",
                    corpus_tier=1,
                    title="哈希长度校验",
                    content_hash=hash_value,
                )
            )
            await db.commit()

    with pytest.raises(IntegrityError):
        asyncio.run(_insert("abc"))
    asyncio.run(_insert("a" * 64))  # 合法值必须能写入
