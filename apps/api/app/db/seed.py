"""Deterministic development database seeder for local development and demos."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    TimelineEventType,
    User,
    UserRole,
)

DEFAULT_ORG_ID = UUID("00000000-0000-0000-0000-000000000000")
COMMANDER_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
RESPONDER_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
OBSERVER_USER_ID = UUID("00000000-0000-0000-0000-000000000003")
DEFAULT_INCIDENT_ID = UUID("00000000-0000-0000-0000-000000000010")


def seed_dev_database(session: Session) -> dict[str, object]:
    """Seed the database with default organization, personas, and initial payment incident."""
    now = datetime.now(timezone.utc)

    # 1. Organization
    org = session.scalar(select(Organization).where(Organization.id == DEFAULT_ORG_ID))
    if org is None:
        org = Organization(
            id=DEFAULT_ORG_ID,
            name="IncidentPilot Demo Org",
            created_at=now,
        )
        session.add(org)
        session.flush()

    # 2. Users / Personas
    commander = session.scalar(select(User).where(User.id == COMMANDER_USER_ID))
    if commander is None:
        commander = User(
            id=COMMANDER_USER_ID,
            organization_id=DEFAULT_ORG_ID,
            subject="auth0|commander",
            email="commander@example.test",
            display_name="Alice (Commander)",
            role=UserRole.INCIDENT_COMMANDER,
            created_at=now,
        )
        session.add(commander)

    responder = session.scalar(select(User).where(User.id == RESPONDER_USER_ID))
    if responder is None:
        responder = User(
            id=RESPONDER_USER_ID,
            organization_id=DEFAULT_ORG_ID,
            subject="auth0|responder",
            email="responder@example.test",
            display_name="Bob (Database Lead)",
            role=UserRole.RESPONDER,
            created_at=now,
        )
        session.add(responder)

    observer = session.scalar(select(User).where(User.id == OBSERVER_USER_ID))
    if observer is None:
        observer = User(
            id=OBSERVER_USER_ID,
            organization_id=DEFAULT_ORG_ID,
            subject="auth0|observer",
            email="observer@example.test",
            display_name="Observer (Auditor)",
            role=UserRole.OBSERVER,
            created_at=now,
        )
        session.add(observer)

    session.flush()

    # 3. Seed Incident
    incident = session.scalar(select(Incident).where(Incident.id == DEFAULT_INCIDENT_ID))
    if incident is None:
        incident = Incident(
            id=DEFAULT_INCIDENT_ID,
            organization_id=DEFAULT_ORG_ID,
            title="Payment Gateway 503 Authorization Outage",
            severity=IncidentSeverity.SEV1,
            status=IncidentStatus.OPEN,
            commander_user_id=COMMANDER_USER_ID,
            opened_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(incident)
        session.flush()

        # Add commander & responder presence
        p_commander = IncidentParticipant(
            incident_id=incident.id,
            user_id=COMMANDER_USER_ID,
            presence_state=PresenceState.JOINED,
            joined_at=now,
        )
        p_responder = IncidentParticipant(
            incident_id=incident.id,
            user_id=RESPONDER_USER_ID,
            presence_state=PresenceState.JOINED,
            joined_at=now,
        )
        session.add_all([p_commander, p_responder])

        # Timeline event
        t_event = TimelineEvent(
            incident_id=incident.id,
            event_type=TimelineEventType.STATUS_CHANGE,
            title="Incident declared as SEV1",
            details="Declared by commander with initial status 'open'",
            created_by_user_id=COMMANDER_USER_ID,
            occurred_at=now,
        )
        session.add(t_event)

        # Audit event
        a_event = AuditEvent(
            organization_id=DEFAULT_ORG_ID,
            incident_id=incident.id,
            actor_type=AuditActorType.USER,
            actor_user_id=COMMANDER_USER_ID,
            event_type="incident.declared",
            payload={
                "title": incident.title,
                "severity": incident.severity.value,
                "status": incident.status.value,
                "commander_user_id": str(COMMANDER_USER_ID),
            },
            occurred_at=now,
        )
        session.add(a_event)

    session.commit()

    return {
        "organization": org,
        "commander": commander,
        "responder": responder,
        "observer": observer,
        "incident": incident,
    }
