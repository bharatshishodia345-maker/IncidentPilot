"""Incident domain service managing lifecycle, participants, and audit events."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.db.models import (
    AuditActorType,
    Incident,
    IncidentParticipant,
    IncidentSeverity,
    IncidentStatus,
    PresenceState,
    TimelineEvent,
    TimelineEventType,
    User,
)
from app.services.audit import AuditService

ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DECLARED: {IncidentStatus.OPEN, IncidentStatus.MITIGATED, IncidentStatus.RESOLVED},
    IncidentStatus.OPEN: {IncidentStatus.MITIGATED, IncidentStatus.RESOLVED},
    IncidentStatus.MITIGATED: {IncidentStatus.OPEN, IncidentStatus.RESOLVED},
    IncidentStatus.RESOLVED: {IncidentStatus.OPEN},  # Reopen incident if necessary
}


class IncidentService:
    """Encapsulates business operations for incidents with strict tenant isolation and audit logging."""

    @staticmethod
    def list_incidents(
        session: Session,
        organization_id: UUID,
        status: IncidentStatus | None = None,
        severity: IncidentSeverity | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        """List incidents strictly scoped to the caller's organization."""
        statement = select(Incident).where(Incident.organization_id == organization_id)
        if status is not None:
            statement = statement.where(Incident.status == status)
        if severity is not None:
            statement = statement.where(Incident.severity == severity)

        statement = statement.order_by(Incident.opened_at.desc()).limit(limit).offset(offset)
        return list(session.scalars(statement).all())

    @staticmethod
    def get_incident(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
    ) -> Incident:
        """Fetch a single incident by ID scoped to the organization, or raise EntityNotFoundError."""
        statement = select(Incident).where(
            Incident.id == incident_id,
            Incident.organization_id == organization_id,
        )
        incident = session.scalar(statement)
        if incident is None:
            raise EntityNotFoundError("Incident", str(incident_id))
        return incident

    @staticmethod
    def create_incident(
        session: Session,
        organization_id: UUID,
        commander_user_id: UUID,
        title: str,
        severity: IncidentSeverity,
        status: IncidentStatus = IncidentStatus.DECLARED,
        actor_user_id: UUID | None = None,
    ) -> Incident:
        """Declare a new incident, add commander as participant, log timeline event and audit record."""
        # Verify commander user exists in this organization
        commander = session.scalar(
            select(User).where(User.id == commander_user_id, User.organization_id == organization_id)
        )
        if commander is None:
            raise EntityNotFoundError("User", str(commander_user_id))

        incident = Incident(
            organization_id=organization_id,
            commander_user_id=commander_user_id,
            title=title.strip(),
            severity=severity,
            status=status,
        )
        session.add(incident)
        session.flush()

        # Add commander as initial joined participant
        participant = IncidentParticipant(
            incident_id=incident.id,
            user_id=commander_user_id,
            presence_state=PresenceState.JOINED,
        )
        session.add(participant)

        # Record timeline event for declaration
        timeline_event = TimelineEvent(
            incident_id=incident.id,
            event_type=TimelineEventType.STATUS_CHANGE,
            title=f"Incident declared as {severity.value.upper()}",
            details=f"Declared by commander with initial status '{status.value}'",
            created_by_user_id=actor_user_id or commander_user_id,
        )
        session.add(timeline_event)

        # Append-only audit record
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER,
            event_type="incident.declared",
            payload={
                "title": incident.title,
                "severity": incident.severity.value,
                "status": incident.status.value,
                "commander_user_id": str(commander_user_id),
            },
            incident_id=incident.id,
            actor_user_id=actor_user_id or commander_user_id,
        )

        session.commit()
        session.refresh(incident)
        return incident

    @staticmethod
    def update_incident_status(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        new_status: IncidentStatus,
        actor_user_id: UUID | None = None,
    ) -> Incident:
        """Transition incident status with validation, updating timestamps, timeline, and audit log."""
        incident = IncidentService.get_incident(session, organization_id, incident_id)

        if incident.status == new_status:
            return incident

        valid_next_states = ALLOWED_TRANSITIONS.get(incident.status, set())
        if new_status not in valid_next_states:
            raise InvalidStateTransitionError(incident.status.value, new_status.value)

        old_status = incident.status
        incident.status = new_status

        if new_status == IncidentStatus.RESOLVED:
            incident.closed_at = datetime.now(timezone.utc)
        elif old_status == IncidentStatus.RESOLVED and new_status != IncidentStatus.RESOLVED:
            incident.closed_at = None

        # Add timeline event
        timeline_event = TimelineEvent(
            incident_id=incident.id,
            event_type=TimelineEventType.STATUS_CHANGE,
            title=f"Status changed from {old_status.value} to {new_status.value}",
            created_by_user_id=actor_user_id,
        )
        session.add(timeline_event)

        # Audit record
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER,
            event_type="incident.status_updated",
            payload={
                "previous_status": old_status.value,
                "new_status": new_status.value,
            },
            incident_id=incident.id,
            actor_user_id=actor_user_id,
        )

        session.commit()
        session.refresh(incident)
        return incident

    @staticmethod
    def join_room(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        user_id: UUID,
    ) -> IncidentParticipant:
        """Join an incident live room, updating presence and emitting audit event."""
        IncidentService.get_incident(session, organization_id, incident_id)

        user = session.scalar(
            select(User).where(User.id == user_id, User.organization_id == organization_id)
        )
        if user is None:
            raise EntityNotFoundError("User", str(user_id))

        participant = session.scalar(
            select(IncidentParticipant).where(
                IncidentParticipant.incident_id == incident_id,
                IncidentParticipant.user_id == user_id,
            )
        )

        now = datetime.now(timezone.utc)
        if participant is None:
            participant = IncidentParticipant(
                incident_id=incident_id,
                user_id=user_id,
                presence_state=PresenceState.JOINED,
                joined_at=now,
                left_at=None,
            )
            session.add(participant)
        else:
            participant.presence_state = PresenceState.JOINED
            participant.joined_at = now
            participant.left_at = None

        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER,
            event_type="incident.room_joined",
            payload={"user_id": str(user_id), "display_name": user.display_name, "role": user.role.value},
            incident_id=incident_id,
            actor_user_id=user_id,
        )

        session.commit()
        session.refresh(participant)
        return participant

    @staticmethod
    def leave_room(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        user_id: UUID,
    ) -> IncidentParticipant | None:
        """Leave an incident live room, updating presence and recording audit event."""
        IncidentService.get_incident(session, organization_id, incident_id)

        participant = session.scalar(
            select(IncidentParticipant).where(
                IncidentParticipant.incident_id == incident_id,
                IncidentParticipant.user_id == user_id,
            )
        )

        if participant is not None:
            participant.presence_state = PresenceState.LEFT
            participant.left_at = datetime.now(timezone.utc)

            AuditService.record_event(
                session=session,
                organization_id=organization_id,
                actor_type=AuditActorType.USER,
                event_type="incident.room_left",
                payload={"user_id": str(user_id)},
                incident_id=incident_id,
                actor_user_id=user_id,
            )

            session.commit()
            session.refresh(participant)

        return participant

    @staticmethod
    def get_room_presence(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
    ) -> list[tuple[IncidentParticipant, User]]:
        """List all participants and their current presence in an incident."""
        IncidentService.get_incident(session, organization_id, incident_id)

        statement = (
            select(IncidentParticipant, User)
            .join(User, IncidentParticipant.user_id == User.id)
            .where(IncidentParticipant.incident_id == incident_id)
            .order_by(IncidentParticipant.joined_at.desc())
        )
        return list(session.execute(statement).all())

