"""AI-Service 对 Backend 暴露的稳定 Agent API 契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentContext(BaseModel):
    """跨 Agent 的最小调用上下文；业务字段应放在各 Agent 的输入模型。"""

    model_config = ConfigDict(populate_by_name=True)
    request_id: str = Field(alias="requestId")
    trace_id: str | None = Field(default=None, alias="traceId")
    user_id: str | None = Field(default=None, alias="userId")
    session_id: str | None = Field(default=None, alias="sessionId")
    task_id: str | None = Field(default=None, alias="taskId")
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegalQaInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class Citation(BaseModel):
    document_id: str | None = None
    kb_chunk_id: str | None = None
    law_name: str | None = None
    article_no: str | None = None
    quoted_text: str | None = None
    relevance_score: float | None = None


class LegalQaResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class AgentInvokeRequest(BaseModel):
    agent_code: str = Field(alias="agentCode")
    input: dict[str, Any]
    context: AgentContext


class AgentInvokeResponse(BaseModel):
    request_id: str = Field(alias="requestId")
    data: dict[str, Any]


class ContractReviewInput(BaseModel):
    plain_text: str = Field(min_length=1)


class RiskPoint(BaseModel):
    risk_level: Literal["high", "medium", "low"]
    risk_category: str | None = None
    clause_title: str | None = None
    clause_text: str | None = None
    description: str
    suggestion: str | None = None
    legal_basis: str | None = None
    source_type: Literal["retrieved_law", "rule", "llm_inference"]


class ContractReviewResult(BaseModel):
    extracted_terms: dict[str, Any]
    risk_points: list[RiskPoint]
