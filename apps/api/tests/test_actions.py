from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from tests.conftest import generate_jwt
from app.actions.schemas import AllowlistedActionType, ProposalStatus, RiskLevel
from app.db.models import AuditActorType, AuditEvent, TimelineEvent, UserRole
from app.services.action_service import ActionService
from app.services.incident_service import IncidentService


def test_propose_allowlisted_action(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    # 1. Create incident
    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Canary Outage", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # 2. Propose allowlisted action: rollback_deployment
    payload = {
        "action_type": "rollback_deployment",
        "title": "Rollback checkout-service to v2.13.9",
        "description": "Revert recent canary release due to 503 spike",
        "risk_level": "high",
        "expires_in_minutes": 15,
        "parameters": {
            "service_name": "checkout-service",
            "target_version": "v2.13.9",
            "cluster": "production-primary",
        },
    }

    prop_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/propose",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prop_resp.status_code == 201
    data = prop_resp.json()
    assert data["action_type"] == "rollback_deployment"
    assert data["status"] == "pending_approval"
    assert data["risk_level"] == "high"
    assert data["idempotency_key"] is not None


def test_action_parameter_validation_rejects_unsafe_inputs(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Security Test Incident", "severity": "sev2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # 1. Reject invalid service name (command injection attempt)
    unsafe_payload = {
        "action_type": "rollback_deployment",
        "title": "Unsafe Rollback",
        "parameters": {
            "service_name": "checkout-service; rm -rf /",
            "target_version": "v2.0",
            "cluster": "production-primary",
        },
    }
    resp = client.post(
        f"/v1/incidents/{incident_id}/actions/propose",
        json=unsafe_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_human_commander_approval_and_sandboxed_execution(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    # 1. Create incident & proposal
    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Approval Flow Incident", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    prop_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/propose",
        json={
            "action_type": "drain_traffic",
            "title": "Drain 50% traffic from degraded region",
            "risk_level": "medium",
            "parameters": {
                "service_name": "payment-api",
                "drain_percentage": 50,
                "region": "eu-central-1",
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    proposal_id = prop_resp.json()["id"]

    # 2. Commander authorizes action
    approve_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        json={"rationale": "High error rate confirmed by telemetry."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approve_resp.status_code == 200
    exec_data = approve_resp.json()
    assert exec_data["status"] == "executed"
    assert exec_data["approved_by_user_id"] == str(commander.id)
    assert exec_data["approved_at"] is not None
    assert exec_data["executed_at"] is not None
    assert exec_data["execution_result"]["status"] == "success"
    assert exec_data["execution_result"]["details"]["drain_percentage"] == 50


def test_replay_protection_prevents_duplicate_approval(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Replay Test Incident", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    prop_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/propose",
        json={
            "action_type": "restart_service",
            "title": "Restart auth pod",
            "parameters": {"service_name": "auth-service", "grace_period_seconds": 15},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    proposal_id = prop_resp.json()["id"]

    # 1. First approval succeeds
    resp1 = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    # 2. Second approval attempt fails with 409 Conflict
    resp2 = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "CONFLICT"
    assert "cannot be approved in 'executed' state" in resp2.json()["detail"]


def test_approval_expiry_blocks_stale_authorizations(session) -> None:
    from app.actions.schemas import ActionProposalCreate, AllowlistedActionType
    from app.core.exceptions import ConflictError
    from app.db.models import IncidentSeverity, Organization, User


    org = Organization(name="Expiry Test Org")
    commander = User(
        organization=org,
        subject="auth0|expirycommander",
        email="commander@expiry.test",
        display_name="Expiry Commander",
        role=UserRole.INCIDENT_COMMANDER,
    )
    session.add_all([org, commander])
    session.commit()

    incident = IncidentService.create_incident(
        session=session,
        organization_id=org.id,
        commander_user_id=commander.id,
        title="Stale Action Test",
        severity=IncidentSeverity.SEV1,
    )

    # Create proposal with expired TTL
    proposal = ActionService.propose_action(
        session=session,
        organization_id=org.id,
        incident_id=incident.id,
        payload=ActionProposalCreate(
            action_type=AllowlistedActionType.SCALE_REPLICAS,
            title="Scale worker pods",
            parameters={"service_name": "worker-pool", "replica_count": 10},
            expires_in_minutes=1,
        ),
    )

    # Force expiration in DB
    proposal.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    session.commit()

    # Attempt to approve expired proposal -> ConflictError
    with pytest.raises(ConflictError) as exc_info:
        ActionService.approve_and_execute_action(
            session=session,
            organization_id=org.id,
            incident_id=incident.id,
            proposal_id=proposal.id,
            approver_user_id=commander.id,
            approver_role=UserRole.INCIDENT_COMMANDER,
        )
    assert "expired" in str(exc_info.value)


def test_responder_cannot_approve_actions(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    responder = seed_data["responder"]

    commander_token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)
    responder_token = generate_jwt(organization_id=org1.id, role=UserRole.RESPONDER, subject=responder.subject)

    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "RBAC Action Test", "severity": "sev1"},
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    incident_id = inc_resp.json()["id"]

    prop_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/propose",
        json={
            "action_type": "rollback_deployment",
            "title": "High risk rollback",
            "risk_level": "critical",
            "parameters": {
                "service_name": "billing-api",
                "target_version": "v1.9.0",
                "cluster": "prod-eu",
            },
        },
        headers={"Authorization": f"Bearer {responder_token}"},
    )
    proposal_id = prop_resp.json()["id"]

    # Responder attempts approval -> 403 Forbidden
    approve_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {responder_token}"},
    )
    assert approve_resp.status_code == 403
    assert approve_resp.json()["code"] == "HTTP_ERROR" or approve_resp.json()["code"] == "PERMISSION_DENIED"


def test_cross_tenant_action_protection(client, seed_data) -> None:
    org1 = seed_data["org1"]
    org2 = seed_data["org2"]
    commander1 = seed_data["commander"]
    commander2 = seed_data["other_commander"]

    token1 = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander1.subject)
    token2 = generate_jwt(organization_id=org2.id, role=UserRole.INCIDENT_COMMANDER, subject=commander2.subject)

    # Org1 creates incident and proposal
    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Org1 Critical Outage", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    incident_id = inc_resp.json()["id"]

    prop_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/propose",
        json={
            "action_type": "restart_service",
            "title": "Restart internal cache",
            "parameters": {"service_name": "cache-service", "grace_period_seconds": 10},
        },
        headers={"Authorization": f"Bearer {token1}"},
    )
    proposal_id = prop_resp.json()["id"]

    # Commander from Org2 attempts to approve Org1 proposal -> 404 Not Found
    cross_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert cross_resp.status_code == 404
    assert cross_resp.json()["code"] == "NOT_FOUND"
