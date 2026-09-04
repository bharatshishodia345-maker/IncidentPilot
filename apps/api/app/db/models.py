"""Core IncidentPilot ORM entities.

These models intentionally contain no AI, media, or automation implementation.
They define the tenant-scoped incident record that later modules can build on.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_column(enum_type: type[Enum], name: str, length: int = 32) -> SqlEnum:
    """Store enum values as portable strings on SQLite and PostgreSQL."""

    return SqlEnum(
        enum_type,
        name=name,
        native_enum=False,
        # The named, explicit constraints below make schema-drift checks
        # deterministic on SQLite and PostgreSQL.
        create_constraint=False,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
        length=length,
    )


class UserRole(str, Enum):
    INCIDENT_COMMANDER = "incident_commander"
    RESPONDER = "responder"
    OBSERVER = "observer"


class IncidentStatus(str, Enum):
    DECLARED = "declared"
    OPEN = "open"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"


class IncidentSeverity(str, Enum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"


class PresenceState(str, Enum):
    JOINED = "joined"
    LEFT = "left"


class ActionStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class TimelineEventType(str, Enum):
    OBSERVATION = "observation"
    DECISION = "decision"
    ACTION = "action"
    STATUS_CHANGE = "status_change"
    NOTE = "note"


class AuditActorType(str, Enum):
    USER = "user"
    SYSTEM = "system"
    AI = "ai"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="organization")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "subject", name="uq_users_organization_subject"),
        CheckConstraint(
            "role IN ('incident_commander', 'responder', 'observer')",
            name="user_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole, "user_role"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="users")
    commanded_incidents: Mapped[list["Incident"]] = relationship(
        back_populates="commander", foreign_keys="Incident.commander_user_id"
    )
    incident_participations: Mapped[list["IncidentParticipant"]] = relationship(back_populates="user")
    owned_actions: Mapped[list["ActionItem"]] = relationship(back_populates="owner")
    timeline_events: Mapped[list["TimelineEvent"]] = relationship(back_populates="created_by")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="actor_user")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('declared', 'open', 'mitigated', 'resolved')",
            name="incident_status",
        ),
        CheckConstraint("severity IN ('sev1', 'sev2', 'sev3', 'sev4')", name="incident_severity"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        enum_column(IncidentStatus, "incident_status"), default=IncidentStatus.DECLARED, nullable=False, index=True
    )
    severity: Mapped[IncidentSeverity] = mapped_column(
        enum_column(IncidentSeverity, "incident_severity"), nullable=False
    )
    commander_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="incidents")
    commander: Mapped[User] = relationship(back_populates="commanded_incidents", foreign_keys=[commander_user_id])
    participants: Mapped[list["IncidentParticipant"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    action_items: Mapped[list["ActionItem"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    action_proposals: Mapped[list["ActionProposal"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    timeline_events: Mapped[list["TimelineEvent"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    knowledge_records: Mapped[list["KnowledgeRecord"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="incident")




class IncidentParticipant(Base):
    __tablename__ = "incident_participants"
    __table_args__ = (
        UniqueConstraint("incident_id", "user_id", name="uq_incident_participant"),
        CheckConstraint("presence_state IN ('joined', 'left')", name="presence_state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    presence_state: Mapped[PresenceState] = mapped_column(
        enum_column(PresenceState, "presence_state"), default=PresenceState.JOINED, nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    incident: Mapped[Incident] = relationship(back_populates="participants")
    user: Mapped[User] = relationship(back_populates="incident_participations")


class ActionItem(Base):
    __tablename__ = "action_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'blocked', 'done')",
            name="action_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[ActionStatus] = mapped_column(
        enum_column(ActionStatus, "action_status"), default=ActionStatus.OPEN, nullable=False, index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    incident: Mapped[Incident] = relationship(back_populates="action_items")
    owner: Mapped[User | None] = relationship(back_populates="owned_actions")


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('observation', 'decision', 'action', 'status_change', 'note')",
            name="timeline_event_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[TimelineEventType] = mapped_column(
        enum_column(TimelineEventType, "timeline_event_type"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="timeline_events")
    created_by: Mapped[User | None] = relationship(back_populates="timeline_events")


class AuditEvent(Base):
    """Append-only application audit record.

    Application services create these records but do not expose update or delete
    operations. Database-level immutable retention can be added for production.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'system', 'ai')", name="audit_actor_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id", ondelete="SET NULL"), index=True)
    actor_type: Mapped[AuditActorType] = mapped_column(
        enum_column(AuditActorType, "audit_actor_type"), nullable=False
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    organization: Mapped[Organization] = relationship(back_populates="audit_events")
    incident: Mapped[Incident | None] = relationship(back_populates="audit_events")
    actor_user: Mapped[User | None] = relationship(back_populates="audit_events")


class ActionProposal(Base):
    """Human-in-the-loop remediation proposal requiring human commander approval."""

    __tablename__ = "action_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'expired', 'executed', 'failed')",
            name="action_proposal_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending_approval", nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    proposed_by_actor_type: Mapped[AuditActorType] = mapped_column(
        enum_column(AuditActorType, "audit_actor_type"), default=AuditActorType.AI, nullable=False
    )
    proposed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="action_proposals")
    organization: Mapped[Organization] = relationship()
    proposed_by: Mapped[User | None] = relationship(foreign_keys=[proposed_by_user_id])
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_user_id])


class KnowledgeRecord(Base):
    """Organization-scoped verified feedback knowledge record derived strictly from validated incident outcomes."""

    __tablename__ = "knowledge_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    incident_id: Mapped[UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    effective_remediation: Mapped[str] = mapped_column(Text, nullable=False)
    preventative_actions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    validated_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    organization: Mapped[Organization] = relationship()
    incident: Mapped[Incident] = relationship(back_populates="knowledge_records")
    validated_by: Mapped[User] = relationship()


