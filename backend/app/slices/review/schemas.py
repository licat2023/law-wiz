"""审查切片的对外契约（Pydantic 模型）。

字段与 05-接口设计 §5.4 的 C-01 ~ C-06 逐字一致；ID 一律为**字符串**（§3.4）。

⚠️ `RiskPointData.source_type` 的三种取值是**契约的一部分**，前端按它区分呈现：
- `retrieved_law` 依据检索到的法条 → 可点击查看原文；
- `rule` 依据人工风险规则 → 标注"依据审查规则"，不冒充法条；
- `llm_inference` 模型推断、**无直接法律依据** → 必须标注"仅供参考"。

三者混为一谈是本项目最容易被质疑的设计缺陷（见 03-概要设计 §5.3）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["high", "medium", "low"]
SourceType = Literal["retrieved_law", "rule", "llm_inference"]
TaskStatus = Literal["pending", "processing", "succeeded", "failed"]


class ReviewCounts(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0


class ExtractedTerms(BaseModel):
    """条款提取结果。

    ⚠️ **宽容解析**：内容是 LLM 产出，字段缺失或多余都应被接受 ——
    因字段问题让整个审查任务失败，是把模型的不可靠性转嫁给了用户。
    """

    model_config = ConfigDict(extra="allow")

    parties: list[str] = Field(default_factory=list)
    amount: str | None = None
    payment_terms: str | None = None
    liability: str | None = None
    jurisdiction: str | None = None
    term: str | None = None


class CreateReviewRequest(BaseModel):
    """C-01 请求体。"""

    file_id: str = Field(description="已上传的文件 ID")
    contract_title: str | None = Field(default=None, max_length=200)
    force: bool = Field(default=False, description="为 true 时允许对同一文件并发多个审查任务")


class ReviewTaskData(BaseModel):
    """C-01 / C-02 的响应。"""

    task_id: str
    status: TaskStatus
    stage: str | None = None
    progress: int = 0
    error_code: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str | None = None


class RiskPointData(BaseModel):
    id: str
    risk_level: RiskLevel
    risk_category: str | None = None
    clause_title: str | None = None
    clause_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    description: str
    suggestion: str | None = None
    legal_basis: str | None = None
    source_type: SourceType
    confidence: float | None = None
    is_dismissed: bool = False


class ReviewResultData(BaseModel):
    """C-03 响应。"""

    task_id: str
    contract_title: str | None = None
    summary: str | None = None
    counts: ReviewCounts
    extracted_terms: dict[str, Any] | None = None
    risk_points: list[RiskPointData]


class ReviewListItem(BaseModel):
    """C-05 列表项。"""

    task_id: str
    contract_title: str | None = None
    status: TaskStatus
    counts: ReviewCounts
    created_at: str
    finished_at: str | None = None


class DismissRiskPointRequest(BaseModel):
    """C-06 请求体。响应即更新后的 `RiskPointData`。"""

    is_dismissed: bool
