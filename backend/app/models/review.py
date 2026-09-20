"""合同智能审查模型（M2，P1）。

对应 04-数据库设计 §5.6 ~ §5.8。

两条关键设计：
1. `stage` 与 `progress` 是为**异步任务 + 轮询**服务的（03-概要设计 §5.1）。
   没有这两个字段，用户面对的是一个无反馈的等待。
2. `risk_point.source_type` 是 03-概要设计 §5.3 那条界面约束的**数据基础** ——
   报告中必须区分「检索到的法律依据」「系统依据规则给出的判断」「模型的解释性表述」。
   **若数据库不区分，前端就无法区分，这条约束就落不了地。**
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.base import (
    BIGINT_PK,
    DATETIME_MS,
    JSON_V,
    MYSQL_TABLE_ARGS,
    SERVER_NOW_MS,
    Base,
    TimestampMixin,
    fk,
)

# risk_point.source_type 的取值（见 CONTEXT.md「依据类型」）
SOURCE_RETRIEVED_LAW = "retrieved_law"
SOURCE_RULE = "rule"
SOURCE_LLM_INFERENCE = "llm_inference"


class ReviewTask(Base, TimestampMixin):
    """一次合同审查的执行实例。"""

    __tablename__ = "review_task"
    __table_args__ = (MYSQL_TABLE_ARGS,)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    # 允许为空：支持"仅上传未建合同"的轻量审查
    contract_id: Mapped[int | None] = mapped_column(
        BIGINT_PK, fk("contract.id", name="fk_review_task_contract"), nullable=True, default=None
    )
    contract_version_id: Mapped[int | None] = mapped_column(
        BIGINT_PK,
        fk("contract_version.id", name="fk_review_task_version"),
        nullable=True,
        default=None,
    )
    user_id: Mapped[int] = mapped_column(BIGINT_PK, fk("user.id", name="fk_review_task_user"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    # ocr / extract_terms / retrieve / analyze / report —— 供前端显示进度
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    extracted_terms: Mapped[dict | None] = mapped_column(JSON_V, nullable=True, default=None)
    # 仅供排错与模型输出质量分析，**不参与任何业务逻辑**（04-数据库设计 §4.4）
    raw_llm_output: Mapped[dict | None] = mapped_column(JSON_V, nullable=True, default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    # 面向用户，不含堆栈
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    started_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)

    risk_points: Mapped[list[RiskPoint]] = relationship(back_populates="task", cascade="all, delete-orphan")
    report: Mapped[ReviewReport | None] = relationship(
        back_populates="task", uselist=False, cascade="all, delete-orphan"
    )


class RiskPoint(Base, TimestampMixin):
    """单条风险点。"""

    __tablename__ = "risk_point"
    __table_args__ = (MYSQL_TABLE_ARGS,)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    review_task_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("review_task.id", name="fk_risk_point_task"), nullable=False
    )
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)  # high/medium/low
    risk_category: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    clause_title: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    clause_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # ⚠️ char_start/char_end 的基准是 contract_version.plain_text（原始文本），
    # 不是 OCR 结果、不是 PDF 页面坐标。前端若用别处的文本做高亮，偏移必然对不上。
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    legal_basis: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # source_type = retrieved_law 时必填（应用层校验，非数据库层，见 04-数据库设计 §4.5）
    kb_document_id: Mapped[int | None] = mapped_column(
        BIGINT_PK, fk("kb_document.id", name="fk_risk_point_kb_doc"), nullable=True, default=None
    )
    # source_type = rule 时必填
    risk_rule_id: Mapped[int | None] = mapped_column(
        BIGINT_PK, fk("risk_rule.id", name="fk_risk_point_rule"), nullable=True, default=None
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True, default=None)
    # 用户驳回误报。**这是收集模型误报样本的唯一途径**（04-数据库设计 §5.7）
    is_dismissed: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)

    task: Mapped[ReviewTask] = relationship(back_populates="risk_points")


class ReviewReport(Base, TimestampMixin):
    """风险审查报告。一个任务一份。"""

    __tablename__ = "review_report"
    __table_args__ = (
        UniqueConstraint("review_task_id", name="uk_review_report_task"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    review_task_id: Mapped[int] = mapped_column(
        BIGINT_PK, fk("review_task.id", name="fk_review_report_task"), nullable=False
    )
    file_object_id: Mapped[int | None] = mapped_column(
        BIGINT_PK, fk("file_object.id", name="fk_review_report_file"), nullable=True, default=None
    )
    format: Mapped[str] = mapped_column(String(8), nullable=False, default="pdf", server_default="pdf")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # 冗余统计，避免列表页反复聚合
    high_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    low_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    generated_at: Mapped[dt.datetime] = mapped_column(
        DATETIME_MS, nullable=False, server_default=SERVER_NOW_MS
    )
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DATETIME_MS, nullable=True, default=None)

    task: Mapped[ReviewTask] = relationship(back_populates="report")
