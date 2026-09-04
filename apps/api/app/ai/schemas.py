"""Pydantic schemas and strict validation models for Incident Intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import TimelineEventType


def default_utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntelligenceSourceType(str, Enum):
    VOICE_TRANSCRIPT = "voice_transcript"
    CHAT_MESSAGE = "chat_message"
    TELEMETRY_LOG = "telemetry_log"
    RESPONDER_OBSERVATION = "responder_observation"


class HypothesisStatus(str, Enum):
    PROPOSED = "proposed"
    INVESTIGATING = "investigating"
    REFUTED = "refuted"
    CONFIRMED = "confirmed"


class ActionUrgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FactItem(BaseModel):
    """A verified, grounded piece of evidence with explicit source attribution."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    statement: str = Field(..., min_length=3, description="Factual, verifiable observation")
    evidence: str = Field(..., min_length=3, description="Direct quote or metric proof verifying the fact")
    source: str = Field(..., min_length=2, description="Speaker, system log, or telemetry source")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    discovered_at: datetime = Field(default_factory=default_utcnow)

    @field_validator("statement", "evidence", "source")
    @classmethod
    def strip_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Field cannot be blank")
        return trimmed


class HypothesisItem(BaseModel):
    """A proposed explanation or potential cause that is tracked separately from facts."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    statement: str = Field(..., min_length=3, description="Hypothesis regarding root cause or behavior")
    proposed_by: str = Field(..., min_length=2, description="Responder who proposed this hypothesis")
    status: HypothesisStatus = Field(default=HypothesisStatus.PROPOSED)
    supporting_evidence: list[str] = Field(default_factory=list)
    refuting_evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=default_utcnow)


class DecisionItem(BaseModel):
    """An explicit operational decision made by a responder or commander."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    decision: str = Field(..., min_length=3, description="Agreed operational choice or strategy")
    decided_by: str = Field(..., min_length=2, description="Responder or commander making the decision")
    rationale: str | None = Field(default=None)
    decided_at: datetime = Field(default_factory=default_utcnow)


class ActionProposalItem(BaseModel):
    """An extracted task or remediation step. Never invents an owner."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(..., min_length=3, description="Specific action item")
    description: str | None = Field(default=None)
    assigned_owner: str | None = Field(
        default=None,
        description="Explicitly named assignee or None if unassigned (must not be fabricated)",
    )
    urgency: ActionUrgency = Field(default=ActionUrgency.MEDIUM)
    requires_approval: bool = Field(
        default=True,
        description="Whether this remediation requires human commander authorization",
    )
    created_at: datetime = Field(default_factory=default_utcnow)


class ConflictItem(BaseModel):
    """Contradiction detected between two responder claims or telemetry sources."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    description: str = Field(..., min_length=5, description="Nature of the contradiction")
    claim_a: str = Field(..., min_length=3)
    source_a: str = Field(..., min_length=2)
    claim_b: str = Field(..., min_length=3)
    source_b: str = Field(..., min_length=2)
    suggested_verification: str | None = Field(default=None)
    detected_at: datetime = Field(default_factory=default_utcnow)


class UnknownItem(BaseModel):
    """Identified knowledge gap or missing telemetry needed for incident resolution."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    question: str = Field(..., min_length=5, description="Missing information or open question")
    impact: str = Field(..., min_length=3, description="Why answering this matters to resolution")
    suggested_inquiry: str = Field(..., min_length=3, description="How responders can verify this")
    identified_at: datetime = Field(default_factory=default_utcnow)


class TimelineProposalItem(BaseModel):
    """A proposed chronological incident timeline milestone."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(..., min_length=3)
    details: str | None = None
    event_type: TimelineEventType = Field(default=TimelineEventType.NOTE)
    occurred_at: datetime = Field(default_factory=default_utcnow)


class ResponseType(str, Enum):
    """Incident Commander conversational action type."""
    CLARIFY = "CLARIFY"
    VERIFY = "VERIFY"
    INVESTIGATE = "INVESTIGATE"
    COORDINATE = "COORDINATE"
    WARN = "WARN"
    RECOMMEND = "RECOMMEND"
    APPROVAL = "APPROVAL"
    CONFIRM = "CONFIRM"


class IncidentIntelligenceOutput(BaseModel):
    """Validated structured intelligence snapshot for an incident."""

    model_config = ConfigDict(from_attributes=True)

    incident_type: str | None = Field(default=None, description="Inferred incident domain category")
    language: str = Field(default="english", description="Detected conversation language (english, hindi, hinglish)")
    response_type: str = Field(default="INVESTIGATE", description="Conversational intent: CLARIFY, VERIFY, INVESTIGATE, COORDINATE, WARN, RECOMMEND, APPROVAL, CONFIRM")
    current_goal: str = Field(default="Understand initial incident impact and symptoms", description="Current active objective of the incident response")
    next_question: str | None = Field(default=None, description="The specific next investigative question asked by the AI commander")
    recommendation: str | None = Field(default=None, description="Proposed safe technical or diagnostic step")
    approval_state: str = Field(default="NONE", description="Approval lifecycle: NONE, PENDING_APPROVAL, APPROVED, EXECUTED")
    resolution_state: str = Field(default="ACTIVE", description="Incident resolution status: ACTIVE, INVESTIGATING, MITIGATING, RECOVERED, RESOLVED")

    facts: list[FactItem] = Field(default_factory=list)
    hypotheses: list[HypothesisItem] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    actions: list[ActionProposalItem] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    unknowns: list[UnknownItem] = Field(default_factory=list)
    timeline_events: list[TimelineProposalItem] = Field(default_factory=list)
    summary: str = Field(..., min_length=5, description="Conversational AI Incident Commander response")
    analyzed_at: datetime = Field(default_factory=default_utcnow)

    @model_validator(mode="after")
    def validate_facts_and_hypotheses_separation(self) -> IncidentIntelligenceOutput:
        """Enforce product principle: facts must have concrete evidence and not be unverified assumptions."""
        for fact in self.facts:
            if not fact.evidence or len(fact.evidence.strip()) < 3:
                raise ValueError(f"Fact '{fact.statement}' lacks required evidence verification.")
        return self


class TranscriptMessage(BaseModel):
    """An individual utterance or telemetry record in the incident stream."""

    speaker: str = Field(..., min_length=1, description="Speaker name or system source")
    text: str = Field(..., min_length=1, description="Transcript or message content")
    timestamp: datetime = Field(default_factory=default_utcnow)
    source_type: IntelligenceSourceType = Field(default=IntelligenceSourceType.VOICE_TRANSCRIPT)


class AnalysisRequest(BaseModel):
    """Request payload for running intelligence analysis over an incident conversation."""

    messages: list[TranscriptMessage] = Field(..., min_length=1, description="Transcript stream to analyze")
    incident_title: str | None = None
    severity: str | None = None
    context_notes: str | None = None
    language: str | None = Field(default=None, description="Previous conversation language hint")
    conversation_turn: int = Field(
        default=1,
        ge=1,
        description="Current conversation turn (1-indexed). Enables turn-aware investigation progression.",
    )
