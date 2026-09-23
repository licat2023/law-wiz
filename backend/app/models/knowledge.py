"""法律知识库模型（M3，P1）。

对应 04-数据库设计 §5.9 ~ §5.12。

三条关键设计：
1. **向量本体不入 MySQL** —— `kb_chunk` 只保存外部向量 ID（`vector_id`），
   向量存放在 VectorStore。使更换向量实现时关系型数据无需迁移（ADR-0004）。
2. **语料分级 `corpus_tier`** —— 检索时可按分级加权或过滤；后期若获得全量语料，
   无需改表结构即可导入。
3. **`kb_chunk` 中刻意冗余 `law_name` / `article_no` / `effective_date`** ——
   检索命中后需要立即给出可读引用并按生效日期过滤已废止法条，每次回表会
   显著增加延迟。代价是语料更新时需同步两处，由导入脚本统一处理。
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now_beijing
from app.infra.db.base import (
    BIGINT_PK,
    DATETIME_MS,
    MYSQL_TABLE_ARGS,
    SERVER_NOW_MS,
    Base,
    TimestampMixin,
    fk,
)

# 语料分级（见 04-数据库设计 §5.9.1 与 03-概要设计 §5.2.1）
TIER_CORE_LAW = 1  # 核心法规：民法典合同编、电子签名法、相关司法解释
TIER_HIGH_VALUE_CASE = 2  # 高价值案例：最高法指导性案例与公报案例中的合同类
TIER_FULL = 3  # 全量案例：**本期不建**（理由见 03-概要设计 §5.2.4）


class KbDocument(Base, TimestampMixin):
    """法律语料元数据。**与"用户上传的文件"（file_object）是完全不同的东西。**"""

    __tablename__ = "kb_document"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uk_kb_document_hash"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)  # law/interpretation/case/template
    corpus_tier: Mapped[int] = mapped_column(
        Integer, nullable=False, default=TIER_CORE_LAW, server_default="1"
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    law_name: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    article_no: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    chapter_path: Mapped[str | None] = mapped_column(String(300), nullable=True, default=None)
    effective_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, default=None)
    # NULL 表示现行有效。检索默认排除已废止法条（见 05-接口设计 §5.5 的 include_abolished）
    abolished_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, default=None)
    revision: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    # 内容 SHA-256（64 位十六进制）。DDL 中另有 CHECK (CHAR_LENGTH = 64) 兜底
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    index_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    indexed_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)

    chunks: Mapped[list[KbChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KbChunk(Base):
    """语料切分块。

    ⚠️ **法律文本必须按条切分，不得按固定字符数硬切**（04-数据库设计 §4.3）。
    按字符数硬切会把一条法条截成两半，检索到半句话会直接导致**错误的法律依据** ——
    这是本项目最不能接受的失败形态。

    `char_start` / `char_end` 保留原文偏移，使检索结果能精确定位回原文，
    支撑"回答溯源"。
    """

    __tablename__ = "kb_chunk"
    __table_args__ = (
        UniqueConstraint("kb_document_id", "chunk_no", name="uk_kb_chunk_doc_no"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    kb_document_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("kb_document.id", name="fk_kb_chunk_document"), nullable=False
    )
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="article", server_default="article"
    )
    # 以下三项为**刻意的反范式冗余**，理由见模块文档字符串
    article_no: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    law_name: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    effective_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, default=None)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    # 外部向量库中的 ID；NULL 表示尚未完成向量化
    vector_id: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(
        DATETIME_MS, nullable=False, default=now_beijing, server_default=SERVER_NOW_MS
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DATETIME_MS,
        nullable=False,
        default=now_beijing,
        onupdate=now_beijing,
        server_default=SERVER_NOW_MS,
    )

    document: Mapped[KbDocument] = relationship(back_populates="chunks")


class RiskRule(Base, TimestampMixin):
    """人工编写的风险规则（「条件—结论—法条依据」）。

    一期计划 30–50 条。它在**检索无结果或模型输出无法解析时**提供可解释的兜底结论
    （03-概要设计 §5.3）。**它不是 AI 的替代品，而是 AI 失效时的保险。**
    """

    __tablename__ = "risk_rule"
    __table_args__ = (
        UniqueConstraint("rule_code", name="uk_risk_rule_code"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(32), nullable=False)  # 如 R-0001
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)
    condition_expr: Mapped[str] = mapped_column(Text, nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    legal_basis: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    match_keywords: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)


class RiskRuleSource(Base):
    """规则与法条的多对多关联。"""

    __tablename__ = "risk_rule_source"
    __table_args__ = (
        UniqueConstraint("risk_rule_id", "kb_document_id", name="uk_risk_rule_source"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    risk_rule_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("risk_rule.id", name="fk_rule_source_rule"), nullable=False
    )
    kb_document_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("kb_document.id", name="fk_rule_source_doc"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DATETIME_MS, nullable=False, default=now_beijing, server_default=SERVER_NOW_MS
    )
