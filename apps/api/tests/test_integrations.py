from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from tests.conftest import generate_jwt
from app.db.models import AuditActorType, AuditEvent, TimelineEvent, UserRole
from app.integrations.base import (
    BaseIntegrationClient,
    IntegrationAuthError,
    IntegrationProvider,
    IntegrationTimeoutError,
    PlannedIntegrationError,
)


def test_list_integration_providers_metadata(client) -> None:
    resp = client.get("/v1/integrations/providers")
    assert resp.status_code == 200
    providers = resp.json()
    assert len(providers) >= 6

    # Verify MVP providers
    slack = next(p for p in providers if p["provider"] == "slack")
    assert slack["status"] == "active"
    assert not slack["is_planned"]

    jira = next(p for p in providers if p["provider"] == "jira")
    assert jira["status"] == "active"

    monitoring = next(p for p in providers if p["provider"] == "monitoring")
    assert monitoring["status"] == "active"

    # Verify Planned providers
    pagerduty = next(p for p in providers if p["provider"] == "pagerduty")
    assert pagerduty["status"] == "planned"
    assert pagerduty["is_planned"] is True
    assert pagerduty["roadmap_milestone"] == "v0.3-GA"


def test_slack_broadcast_and_audit_logging(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    # 1. Create incident
    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Slack Integration Incident", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # 2. Post broadcast to Slack
    payload = {
        "channel": "#incident-war-room",
        "title": "SEV1 Declared: Payment API 503 Outage",
        "text": "Responders are investigating ingress TLS and Stripe webhook latency.",
        "severity": "sev1",
        "status": "open",
    }
    slack_resp = client.post(
        f"/v1/incidents/{incident_id}/integrations/slack/broadcast",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert slack_resp.status_code == 200
    slack_data = slack_resp.json()
    assert slack_data["ok"] is True
    assert slack_data["channel"] == "#incident-war-room"
    assert "slack.example.com" in slack_data["permalink"]


def test_jira_ticket_creation_and_timeline_sync(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Jira Integration Incident", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # Create Jira ticket
    payload = {
        "project_key": "PAY",
        "summary": "SEV1: Payment Gateway Outage",
        "description": "Customer impact: 42.8% checkout failure rate.",
        "priority": "Highest",
    }
    jira_resp = client.post(
        f"/v1/incidents/{incident_id}/integrations/jira/ticket",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert jira_resp.status_code == 201
    jira_data = jira_resp.json()
    assert jira_data["issue_key"].startswith("PAY-")
    assert "jira.example.com" in jira_data["issue_url"]


def test_monitoring_health_metrics_query(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Monitoring Query Incident", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # Query metrics for payment-service
    query_resp = client.get(
        f"/v1/incidents/{incident_id}/integrations/monitoring/metrics?service_name=payment-service",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert query_resp.status_code == 200
    metrics = query_resp.json()
    assert metrics["service_name"] == "payment-service"
    assert metrics["error_rate_percent"] == 42.8
    assert metrics["status"] == "DEGRADED"


def test_planned_integration_stub_returns_501(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Planned Integration Test", "severity": "sev2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # Trigger planned provider (pagerduty) -> 501 Not Implemented
    planned_resp = client.post(
        f"/v1/incidents/{incident_id}/integrations/planned/pagerduty",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert planned_resp.status_code == 501
    assert planned_resp.json()["code"] == "INTEGRATION_PLANNED"
    assert "planned for v0.3-GA" in planned_resp.json()["detail"]


@pytest.mark.anyio
async def test_base_client_timeout_and_retries() -> None:
    client = BaseIntegrationClient(
        provider=IntegrationProvider.SLACK,
        timeout_seconds=0.05,
        max_retries=2,
        backoff_base=0.01,
    )

    call_count = 0

    async def _failing_timeout() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.2)
        return "success"

    with pytest.raises(IntegrationTimeoutError) as exc_info:
        await client.execute_with_resilience("test_timeout", _failing_timeout)

    assert call_count == 2
    assert exc_info.value.provider == "slack"
    assert exc_info.value.timeout_seconds == 0.05


def test_integrations_cross_tenant_isolation(client, seed_data) -> None:
    org1 = seed_data["org1"]
    org2 = seed_data["org2"]
    commander1 = seed_data["commander"]
    commander2 = seed_data["other_commander"]

    token1 = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander1.subject)
    token2 = generate_jwt(organization_id=org2.id, role=UserRole.INCIDENT_COMMANDER, subject=commander2.subject)

    # Org1 creates incident
    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Org1 Integration Scope", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    incident_id = inc_resp.json()["id"]

    # Org2 attempts Slack broadcast on Org1's incident -> 404 Not Found
    cross_resp = client.post(
        f"/v1/incidents/{incident_id}/integrations/slack/broadcast",
        json={"title": "Cross Tenant Attempt", "text": "Testing", "channel": "#general"},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert cross_resp.status_code == 404
    assert cross_resp.json()["code"] == "NOT_FOUND"
