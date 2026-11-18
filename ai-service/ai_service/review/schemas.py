"""合同审查 Agent 的输入和结构化模型输出。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_service.citations import Citation


class ContractTerms(BaseModel):
    """LLM 条款提取的结构化输出；允许未来扩展字段。"""

    model_config = ConfigDict(extra="allow")
    parties: list[str] = Field(default_factory=list)
    amount: str | None = None
    payment_terms: str | None = None
    liability: str | None = None
    jurisdiction: str | None = None
    term: str | None = None


# 模型输出的风险点；引用由节点按本次召回的文档和分块标识校验。
class RiskPoint(BaseModel):
    citations: list[Citation] = Field(default_factory=list)
    risk_level: Literal["high", "medium", "low"]
    risk_category: str | None = None
    clause_title: str | None = None
    clause_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    description: str
    suggestion: str | None = None
    legal_basis: str | None = None
    source_type: Literal["retrieved_law", "rule", "llm_inference"]
    confidence: float | None = None


class ContractRiskAnalysis(BaseModel):
    risk_points: list[RiskPoint] = Field(default_factory=list)


class ContractReviewResult(BaseModel):
    extracted_terms: dict[str, Any]
    risk_points: list[RiskPoint]


class RiskRule(RiskPoint):
    source_type: Literal["rule"] = "rule"


# 审查输入包含本地提取的合同正文和预先匹配的人工规则。
class ContractReviewInput(BaseModel):
    plain_text: str = Field(min_length=1, max_length=200000)
    risk_rules: list[RiskRule] = Field(default_factory=list, max_length=1000)
