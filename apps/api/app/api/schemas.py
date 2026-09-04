"""Public API request and response schemas with strict input validation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import IncidentSeverity, IncidentStatus, PresenceState, UserRole


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str
    environment: str


class IncidentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    title: str
    status: IncidentStatus
    severity: IncidentSeverity
    commander_user_id: UUID
    opened_at: datetime
    closed_at: datetime | None = None


class TimelineEventDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    title: str
    details: str | None = None
    occurred_at: datetime


class IncidentDetail(IncidentSummary):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime
    timeline_events: list[TimelineEventDetail] = Field(default_factory=list)


class IncidentCreate(BaseModel):
    """Schema for declaring a new technical incident."""

    title: str = Field(..., min_length=3, max_length=300, description="Concise summary of the incident")
    severity: IncidentSeverity = Field(..., description="Assessed incident severity level")
    status: IncidentStatus = Field(default=IncidentStatus.DECLARED, description="Initial incident lifecycle status")
    commander_user_id: UUID | None = Field(
        default=None, description="Assigned incident commander user ID; defaults to caller if omitted"
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) < 3:
            raise ValueError("title must contain at least 3 non-whitespace characters")
        return trimmed


class IncidentStatusUpdate(BaseModel):
    """Schema for transitioning an incident status."""

    status: IncidentStatus = Field(..., description="Target lifecycle status")


class ParticipantPresence(BaseModel):
    """Real-time presence snapshot for an incident participant."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    display_name: str
    email: str
    role: UserRole
    presence_state: PresenceState
    joined_at: datetime
    left_at: datetime | None = None


class RoomJoinResponse(BaseModel):
    """Response returned when an authenticated participant joins the incident voice room."""

    app_id: str
    channel_name: str
    token: str
    rtm_token: str | None = None
    agent_id: str | None = None
    agent_status: str | None = None
    agent_mode: str | None = None
    uid: str
    role: UserRole
    is_publisher: bool
    expires_in_seconds: int
    participants: list[ParticipantPresence]


class RoomLeaveResponse(BaseModel):
    """Response returned when leaving the incident room."""

    incident_id: UUID
    user_id: UUID
    status: str = "left"


class AgoraTokenResponse(BaseModel):
    """Refreshed or dedicated Agora RTC token."""

    app_id: str
    channel_name: str
    token: str
    rtm_token: str | None = None
    agent_id: str | None = None
    uid: str
    expires_in_seconds: int


class AgentStatusResponse(BaseModel):
    """Response representing the active Agora Conversational AI agent state."""

    channel: str
    agent_id: str | None = None
    status: str
    mode: str
    agent_rtc_uid: str = "999"
    error_message: str | None = None


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    detail: str
    code: str
    errors: list[ErrorDetail] | None = None
