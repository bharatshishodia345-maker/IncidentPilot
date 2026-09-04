from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.db.models import (
    AuditActorType,
    AuditEvent,
    Incident,
    IncidentParticipant,
    IncidentSeverity,
    IncidentStatus,
    Organization,
    PresenceState,
    TimelineEvent,
    User,
    UserRole,
)
from app.services.audit import AuditService
from app.services.incident_service import IncidentService


def test_audit_service_records_event(session) -> None:
    org = Organization(name="Audit Test Org")
    user = User(
        organization=org,
        subject="auth0|audituser",
        email="audit@example.test",
        display_name="Audit User",
        role=UserRole.RESPONDER,
    )
    session.add_all([org, user])
    session.commit()

    event = AuditService.record_event(
        session=session,
        organization_id=org.id,
        actor_type=AuditActorType.USER,
        event_type="test.action_executed",
        payload={"key": "value"},
        actor_user_id=user.id,
    )
    session.commit()

    stored_event = session.scalar(select(AuditEvent).where(AuditEvent.id == event.id))
    assert stored_event is not None
    assert stored_event.event_type == "test.action_executed"
    assert stored_event.payload == {"key": "value"}
    assert stored_event.organization_id == org.id


def test_incident_service_creates_incident_with_audit_and_timeline(session) -> None:
    org = Organization(name="Service Test Org")
    commander = User(
        organization=org,
        subject="auth0|commander",
        email="commander@service.test",
        display_name="Commander",
        role=UserRole.INCIDENT_COMMANDER,
    )
    session.add_all([org, commander])
    session.commit()

    incident = IncidentService.create_incident(
        session=session,
        organization_id=org.id,
        commander_user_id=commander.id,
        title="Checkout failure spike",
        severity=IncidentSeverity.SEV1,
    )

    assert incident.id is not None
    assert incident.status == IncidentStatus.DECLARED

    # Verify participant was added
    participant = session.scalar(
        select(IncidentParticipant).where(
            IncidentParticipant.incident_id == incident.id,
            IncidentParticipant.user_id == commander.id,
        )
    )
    assert participant is not None
    assert participant.presence_state == PresenceState.JOINED

    # Verify timeline event was added
    timeline = session.scalars(
        select(TimelineEvent).where(TimelineEvent.incident_id == incident.id)
    ).all()
    assert len(timeline) >= 1

    # Verify audit event was logged
    audit = session.scalar(
        select(AuditEvent).where(
            AuditEvent.incident_id == incident.id,
            AuditEvent.event_type == "incident.declared",
        )
    )
    assert audit is not None
    assert audit.payload["severity"] == "sev1"


def test_incident_service_rejects_invalid_state_transition(session) -> None:
    org = Organization(name="Transition Test Org")
    commander = User(
        organization=org,
        subject="auth0|commander",
        email="commander@trans.test",
        display_name="Commander",
        role=UserRole.INCIDENT_COMMANDER,
    )
    session.add_all([org, commander])
    session.commit()

    incident = IncidentService.create_incident(
        session=session,
        organization_id=org.id,
        commander_user_id=commander.id,
        title="Valid to resolved",
        severity=IncidentSeverity.SEV2,
    )

    # Transition to RESOLVED
    IncidentService.update_incident_status(session, org.id, incident.id, IncidentStatus.RESOLVED)
    assert incident.status == IncidentStatus.RESOLVED

    # Cannot transition directly from RESOLVED to MITIGATED (only OPEN is allowed)
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        IncidentService.update_incident_status(session, org.id, incident.id, IncidentStatus.MITIGATED)
    assert "Cannot transition incident status" in str(exc_info.value)


def test_incident_service_raises_on_nonexistent_incident(session) -> None:
    with pytest.raises(EntityNotFoundError):
        IncidentService.get_incident(session, organization_id=uuid4(), incident_id=uuid4())
