from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.conftest import generate_jwt
from app.ai.provider import DeterministicIntelligenceEngine
from app.ai.schemas import (
    AnalysisRequest,
    HypothesisStatus,
    IntelligenceSourceType,
    TranscriptMessage,
)
from app.db.models import AuditActorType, AuditEvent, UserRole
from app.services.intelligence_service import IntelligenceService


@pytest.mark.anyio
async def test_intelligence_extracts_facts_with_evidence_and_separates_hypotheses() -> None:
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    messages = [
        TranscriptMessage(
            speaker="Datadog Alert",
            text="Payment failures jumped 48.5% across checkout service with HTTP 503 responses.",
            source_type=IntelligenceSourceType.TELEMETRY_LOG,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Bob",
            text="I suspect database latency spiked because of the new index build.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
    ]

    request = AnalysisRequest(messages=messages, incident_title="Payment Outage")
    output = await engine.analyze(request)

    # 1. Verify Facts
    assert len(output.facts) >= 1
    fact = output.facts[0]
    assert "48.5%" in fact.statement or "503" in fact.statement
    assert "Datadog Alert" in fact.source
    assert len(fact.evidence) > 0  # Mandatory evidence citation

    # 2. Verify Hypotheses (Bob's speculation must be classified as hypothesis, NOT fact)
    assert len(output.hypotheses) == 1
    hypothesis = output.hypotheses[0]
    assert "Bob" in hypothesis.proposed_by
    assert hypothesis.status == HypothesisStatus.PROPOSED
    assert "database latency" in hypothesis.statement.lower()

    # Fact list must NOT contain Bob's hypothesis
    assert not any("suspect" in f.statement.lower() for f in output.facts)


@pytest.mark.anyio
async def test_intelligence_does_not_fabricate_action_owners() -> None:
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    messages = [
        TranscriptMessage(
            speaker="Alice",
            text="We need to rollback canary deployment v2.14 immediately.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Alice",
            text="Action item: @dave please inspect the redis connection pool.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
    ]

    output = await engine.analyze(AnalysisRequest(messages=messages))
    assert len(output.actions) == 2

    # Unassigned action must have assigned_owner = None
    unassigned_action = next(a for a in output.actions if "rollback" in a.title.lower())
    assert unassigned_action.assigned_owner is None

    # Explicitly assigned action has owner Dave
    assigned_action = next(a for a in output.actions if "redis" in a.title.lower())
    assert assigned_action.assigned_owner.lower() == "dave"


@pytest.mark.anyio
async def test_intelligence_detects_conflicting_telemetry_claims() -> None:
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    messages = [
        TranscriptMessage(
            speaker="Bob",
            text="Database latency is 4500ms and DB pool saturated.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Charlie",
            text="Wait, database is healthy and database CPU is at 12%.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
    ]

    output = await engine.analyze(AnalysisRequest(messages=messages))
    assert len(output.conflicts) >= 1
    conflict = output.conflicts[0]
    assert "database" in conflict.description.lower()
    assert "Bob" in conflict.source_a or "Bob" in conflict.source_b
    assert "Charlie" in conflict.source_a or "Charlie" in conflict.source_b


@pytest.mark.anyio
async def test_intelligence_detects_missing_information_unknowns() -> None:
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    messages = [
        TranscriptMessage(
            speaker="Alice",
            text="Does anyone know if the EU payment gateway token was rotated today?",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
    ]

    output = await engine.analyze(AnalysisRequest(messages=messages))
    assert len(output.unknowns) >= 1
    unknown = output.unknowns[0]
    assert "rotated" in unknown.question.lower() or "token" in unknown.question.lower()


@pytest.mark.anyio
async def test_intelligence_service_records_audit_event(session) -> None:
    from app.services.incident_service import IncidentService
    from app.db.models import IncidentSeverity, Organization, User, UserRole

    org = Organization(name="Intelligence Audit Org")
    commander = User(
        organization=org,
        subject="auth0|intelcommander",
        email="intel@audit.test",
        display_name="Intel Commander",
        role=UserRole.INCIDENT_COMMANDER,
    )
    session.add_all([org, commander])
    session.commit()

    incident = IncidentService.create_incident(
        session=session,
        organization_id=org.id,
        commander_user_id=commander.id,
        title="Intelligence Audit Test",
        severity=IncidentSeverity.SEV1,
    )


    service = IntelligenceService()
    now = datetime.now(timezone.utc)
    request = AnalysisRequest(
        messages=[
            TranscriptMessage(
                speaker="Monitoring",
                text="Payment failures reached 35.0% error rate.",
                timestamp=now,
            )
        ]
    )

    output = await service.analyze_incident_stream(
        session=session,
        organization_id=org.id,
        incident_id=incident.id,
        request=request,
        actor_user_id=commander.id,
    )


    assert len(output.facts) >= 1

    # Verify AuditEvent was persisted
    from sqlalchemy import select
    audit_events = session.scalars(
        select(AuditEvent).where(
            AuditEvent.incident_id == incident.id,
            AuditEvent.event_type == "incident.intelligence_analyzed",
        )
    ).all()

    assert len(audit_events) == 1
    audit = audit_events[0]
    assert audit.actor_type == AuditActorType.AI
    assert audit.payload["facts_count"] >= 1


def test_payment_demo_endpoint(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    # 1. Create incident
    create_resp = client.post(
        "/v1/incidents",
        json={"title": "Payment Outage E2E Demo", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = create_resp.json()["id"]

    # 2. Call payment demo intelligence endpoint
    demo_resp = client.get(
        f"/v1/incidents/{incident_id}/intelligence/payment-demo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert demo_resp.status_code == 200
    data = demo_resp.json()

    assert len(data["facts"]) >= 1
    assert len(data["hypotheses"]) >= 1
    assert len(data["conflicts"]) >= 1
    assert len(data["unknowns"]) >= 1
    assert len(data["actions"]) >= 1
    assert "summary" in data
