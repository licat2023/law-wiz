"""Serializable, bounded report context supplied by the business backend."""

from typing import Literal

from pydantic import BaseModel, Field


class ReportFinding(BaseModel):
    """A bounded finding already saved in the report."""

    risk_level: Literal["high", "medium", "low"]
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=480)
    suggestion: str | None = Field(default=None, max_length=480)


class ReviewFollowupContext(BaseModel):
    contract_title: str | None = Field(max_length=512)
    summary: str | None = Field(max_length=4000)
    risk_label: str | None = Field(default=None, max_length=512)
    risk_description: str | None = Field(default=None, max_length=4000)
    clause_text: str | None = Field(default=None, max_length=4000)
    original_reference: str | None = Field(default=None, max_length=4000)
    source_type: str | None = None
    is_dismissed: bool = False
    findings: list[ReportFinding] = Field(default_factory=list, max_length=8)
