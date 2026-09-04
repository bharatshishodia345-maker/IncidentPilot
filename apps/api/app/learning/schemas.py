"""Schemas for verified-feedback learning layer and organization knowledge base."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OutcomeValidationRequest(BaseModel):
    """Payload submitted by Incident Commander to validate an incident's verified outcome."""

    summary: str = Field(..., min_length=10, max_length=3000, description="Post-incident executive summary")
    root_cause: str = Field(..., min_length=10, max_length=3000, description="Empirically verified root cause")
    effective_remediation: str = Field(
        ..., min_length=5, max_length=3000, description="Remediation actions that stabilized the system"
    )
    preventative_actions: list[str] = Field(default_factory=list, description="Follow-up action items to prevent recurrence")
    tags: list[str] = Field(default_factory=list, description="Categorization tags, e.g. ['database', 'stripe', 'canary']")


class KnowledgeRecordDetail(BaseModel):
    """Organization-scoped verified knowledge record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    incident_id: UUID
    summary: str
    root_cause: str
    effective_remediation: str
    preventative_actions: list[str]
    tags: list[str]
    validated_by_user_id: UUID
    validated_at: datetime
    created_at: datetime


class HistoricalContextItem(BaseModel):
    """Historical knowledge surfaced for context without treating it as a current fact."""

    record_id: UUID
    incident_title: str
    verified_root_cause: str
    effective_remediation: str
    tags: list[str]
    disclaimer: str = Field(
        default="HISTORICAL REFERENCE ONLY — Must not be assumed as current incident root cause without fresh evidence."
    )
