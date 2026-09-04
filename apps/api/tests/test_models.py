from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    ActionItem,
    ActionStatus,
    AuditActorType,
    AuditEvent,
    Incident,
    IncidentParticipant,
    IncidentSeverity,
    IncidentStatus,
    Organization,
    PresenceState,
    TimelineEvent,
    TimelineEventType,
    User,
    UserRole,
)


def test_core_incident_entities_persist_with_relationships(session) -> None:
    organization = Organization(name="Example Payments")
    commander = User(
        organization=organization,
        subject="auth0|commander",
        email="commander@example.test",
        display_name="Incident Commander",
        role=UserRole.INCIDENT_COMMANDER,
    )
    responder = User(
        organization=organization,
        subject="auth0|responder",
        email="responder@example.test",
        display_name="Payment Responder",
        role=UserRole.RESPONDER,
    )
    incident = Incident(
        organization=organization,
        commander=commander,
        title="Payment authorization failures",
        severity=IncidentSeverity.SEV1,
        status=IncidentStatus.OPEN,
    )
    participant = IncidentParticipant(
        incident=incident,
        user=responder,
        presence_state=PresenceState.JOINED,
    )
    action = ActionItem(
        incident=incident,
        owner=responder,
        title="Inspect database latency",
        status=ActionStatus.IN_PROGRESS,
    )
    timeline_event = TimelineEvent(
        incident=incident,
        created_by=responder,
        event_type=TimelineEventType.OBSERVATION,
        title="Payment failures increased",
    )
    audit_event = AuditEvent(
        organization=organization,
        incident=incident,
        actor_type=AuditActorType.USER,
        actor_user=responder,
        event_type="incident.participant_joined",
        payload={"source": "test"},
    )
    session.add_all([organization, commander, responder, incident, participant, action, timeline_event, audit_event])
    session.commit()

    stored_incident = session.scalar(select(Incident).where(Incident.id == incident.id))
    assert stored_incident is not None
    assert stored_incident.organization_id == organization.id
    assert stored_incident.commander_user_id == commander.id
    assert stored_incident.participants == [participant]
    assert stored_incident.action_items == [action]
    assert stored_incident.timeline_events == [timeline_event]
    assert stored_incident.audit_events == [audit_event]
    assert audit_event.payload == {"source": "test"}


def test_incident_participant_cannot_be_added_twice(session) -> None:
    organization = Organization(name="Unique Participant Org")
    commander = User(
        organization=organization,
        subject="auth0|commander",
        email="commander@unique.test",
        display_name="Commander",
        role=UserRole.INCIDENT_COMMANDER,
    )
    responder = User(
        organization=organization,
        subject="auth0|responder",
        email="responder@unique.test",
        display_name="Responder",
        role=UserRole.RESPONDER,
    )
    incident = Incident(
        organization=organization,
        commander=commander,
        title="Duplicate participant protection",
        severity=IncidentSeverity.SEV2,
    )
    session.add_all([organization, commander, responder, incident])
    session.commit()

    session.add_all(
        [
            IncidentParticipant(incident=incident, user=responder),
            IncidentParticipant(incident=incident, user=responder),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

