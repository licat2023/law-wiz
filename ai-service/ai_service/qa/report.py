"""Serializable, bounded report context supplied by the business backend."""

from pydantic import BaseModel, Field


class ReviewFollowupContext(BaseModel):
    contract_title: str | None = Field(max_length=512)
    summary: str | None = Field(max_length=4000)
    risk_label: str | None = Field(default=None, max_length=512)
    risk_description: str | None = Field(default=None, max_length=4000)
    clause_text: str | None = Field(default=None, max_length=4000)
    original_reference: str | None = Field(default=None, max_length=4000)
    source_type: str | None = None
    is_dismissed: bool = False
