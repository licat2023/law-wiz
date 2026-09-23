"""add missing indexes and check constraints

补齐 04-数据库设计 里定义、而前两条迁移漏掉的 10 条索引与 1 条 CHECK；
同时把 `updated_at` 的"更新时刷新"交回 DDL（`ON UPDATE CURRENT_TIMESTAMP(3)`）。

⚠️ `ON UPDATE` 取的是 **MySQL 会话时区**，所以本迁移必须与
`deploy/docker-compose.*.yml` 里 MySQL 的 `--default-time-zone=+08:00` 一起上线：
应用存的是北京时间（`core/clock.py`），服务器时区若不是 +08:00，
同一个库里会混进两种时间口径。

⚠️ 建索引在**有数据的库上会短暂锁表**。当前数据量可忽略；将来若在真实数据上重跑，
应先评估窗口期。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "49fc6db4b015"
down_revision: str | None = "18aa07f432ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 含 `updated_at` 的表（建模时由 TimestampMixin 提供，kb_chunk 为内联定义）
_UPDATED_AT_TABLES = (
    "user",
    "user_profile",
    "file_object",
    "contract",
    "kb_document",
    "kb_chunk",
    "risk_rule",
    "review_task",
    "risk_point",
    "review_report",
    "qa_session",
)


def upgrade() -> None:
    # --- 1. 补齐索引 ---
    # 04-数据库设计 §5.4 / §5.6 / §5.7 / §5.9 / §5.10 / §5.11 / §5.13 / §5.14。
    # 其余单列索引由外键自动生成（名字不同），无需显式创建。
    op.create_index("idx_contract_owner_status", "contract", ["owner_id", "status", "created_at"])
    op.create_index("idx_kb_chunk_vector", "kb_chunk", ["vector_id"])
    op.create_index("idx_kb_document_article", "kb_document", ["law_name", "article_no"])
    op.create_index("idx_kb_document_status", "kb_document", ["index_status"])
    op.create_index("idx_kb_document_type_tier", "kb_document", ["doc_type", "corpus_tier"])
    op.create_index("idx_qa_message_session", "qa_message", ["qa_session_id", "id"])
    op.create_index("idx_qa_session_user", "qa_session", ["user_id", "last_message_at"])
    op.create_index("idx_review_task_user_status", "review_task", ["user_id", "status", "created_at"])
    op.create_index("idx_risk_point_task_level", "risk_point", ["review_task_id", "risk_level"])
    op.create_index("idx_risk_rule_active", "risk_rule", ["is_active", "risk_level"])

    # --- 2. 补齐 CHECK ---
    # 04-数据库设计 §4.5：`content_hash` 必须是 64 位十六进制。
    # ⚠️ 用 `length()`（字节长度）而不是文档里的 `CHAR_LENGTH()`：对十六进制字符串
    #    两者等价，而 `length()` 在 SQLite 上也可用 —— 测试是**从 metadata 建表**的，
    #    写死 MySQL 专有函数会让建表直接失败。
    # ⚠️ 用 `op.f()` 固定名字：模型侧的 `CheckConstraint(name="hash_len")` 会被
    #    命名约定展开成 `ck_kb_document_hash_len`，这里必须落地成同一个名字，
    #    否则模型与数据库对不上（autogenerate 会反复提议重建）。
    op.create_check_constraint(
        op.f("ck_kb_document_hash_len"), "kb_document", "length(content_hash) = 64"
    )

    # --- 3. `updated_at` 交回 DDL 维护 ---
    # 应用侧已有 ORM 的 `onupdate`；这里补上 DDL 级行为，使**绕过 ORM 的裸 SQL UPDATE**
    # （运维脚本、数据修复）也会刷新时间戳。
    for table in _UPDATED_AT_TABLES:
        op.execute(
            f"ALTER TABLE `{table}` MODIFY `updated_at` DATETIME(3) NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"
        )


def downgrade() -> None:
    for table in _UPDATED_AT_TABLES:
        op.execute(
            f"ALTER TABLE `{table}` MODIFY `updated_at` DATETIME(3) NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP(3)"
        )
    op.drop_constraint(op.f("ck_kb_document_hash_len"), "kb_document", type_="check")

    # ⚠️ 这 5 条索引的首列是外键列，**顺序与前置动作都不能照抄 autogenerate 的产物**：
    # MySQL 会拿它们当外键的支撑索引，于是升级时把外键自动生成的单列索引（名即约束名）
    # 删掉了；降级若直接 `DROP INDEX` 会报 `1553 needed in a foreign key constraint`。
    # 而"先建回单列索引"只在第一次降级成立 —— 跑过一轮 upgrade↔downgrade 之后，
    # 那条索引可能还在，重建就会撞 `1061 Duplicate key name`（两种情况都实测过）。
    # 因此走"**拆外键 → 删我们的索引 → 重建外键**"：重建时 MySQL 会自己补回支撑索引，
    # 无论有没有残留都能回到迁移前的形状。
    for index_name, table, fk_name, column, ref_table, ref_column in (
        ("idx_contract_owner_status", "contract", "fk_contract_owner", "owner_id", "user", "id"),
        ("idx_review_task_user_status", "review_task", "fk_review_task_user", "user_id", "user", "id"),
        (
            "idx_risk_point_task_level",
            "risk_point",
            "fk_risk_point_task",
            "review_task_id",
            "review_task",
            "id",
        ),
        ("idx_qa_session_user", "qa_session", "fk_qa_session_user", "user_id", "user", "id"),
        (
            "idx_qa_message_session",
            "qa_message",
            "fk_qa_message_session",
            "qa_session_id",
            "qa_session",
            "id",
        ),
    ):
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.drop_index(index_name, table_name=table)
        op.create_foreign_key(fk_name, table, ref_table, [column], [ref_column])

    for index_name, table in (
        ("idx_risk_rule_active", "risk_rule"),
        ("idx_kb_document_type_tier", "kb_document"),
        ("idx_kb_document_status", "kb_document"),
        ("idx_kb_document_article", "kb_document"),
        ("idx_kb_chunk_vector", "kb_chunk"),
    ):
        op.drop_index(index_name, table_name=table)
