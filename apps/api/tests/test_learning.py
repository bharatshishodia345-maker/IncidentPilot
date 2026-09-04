from __future__ import annotations

from tests.conftest import generate_jwt
from app.db.models import UserRole


def test_validate_incident_outcome_on_resolved_incident(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    # 1. Create incident
    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "EU Payment Latency Spike", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # 2. Transition to mitigated -> resolved
    client.patch(
        f"/v1/incidents/{incident_id}/status",
        json={"status": "mitigated"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.patch(
        f"/v1/incidents/{incident_id}/status",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 3. Commander validates post-incident outcome
    payload = {
        "summary": "EU payment gateway suffered 503 errors due to expired TLS certificate on the ingress proxy.",
        "root_cause": "Automatic cert-manager renewal failed due to DNS challenge rate limiting.",
        "effective_remediation": "Manually renewed TLS certificate and refreshed ingress pods.",
        "preventative_actions": [
            "Increase DNS challenge TTL",
            "Set up certificate expiration alerts 30 days prior",
        ],
        "tags": ["payment", "tls", "ingress", "certificate"],
    }

    val_resp = client.post(
        f"/v1/incidents/{incident_id}/learnings/validate",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert val_resp.status_code == 201
    record = val_resp.json()
    assert record["incident_id"] == incident_id
    assert record["root_cause"] == payload["root_cause"]
    assert "certificate" in record["tags"]


def test_cannot_validate_outcome_on_open_incident(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    # 1. Create incident in OPEN state
    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "Unresolved Live Outage", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = inc_resp.json()["id"]

    # 2. Attempt to validate outcome while open -> 409 Conflict
    payload = {
        "summary": "Premature validation attempt.",
        "root_cause": "Unknown root cause.",
        "effective_remediation": "None yet.",
        "tags": ["testing"],
    }
    val_resp = client.post(
        f"/v1/incidents/{incident_id}/learnings/validate",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert val_resp.status_code == 409
    assert val_resp.json()["code"] == "CONFLICT"
    assert "must be mitigated or resolved" in val_resp.json()["detail"]



def test_responder_cannot_validate_outcome(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    responder = seed_data["responder"]

    commander_token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)
    responder_token = generate_jwt(organization_id=org1.id, role=UserRole.RESPONDER, subject=responder.subject)

    # Create & resolve incident
    inc_resp = client.post(
        "/v1/incidents",
        json={"title": "RBAC Learning Test", "severity": "sev2"},
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    incident_id = inc_resp.json()["id"]

    client.patch(
        f"/v1/incidents/{incident_id}/status",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {commander_token}"},
    )

    # Responder attempts validation -> 403 Forbidden
    payload = {
        "summary": "Responder submitted summary.",
        "root_cause": "Responder root cause.",
        "effective_remediation": "Reboot.",
        "tags": ["rbac"],
    }
    val_resp = client.post(
        f"/v1/incidents/{incident_id}/learnings/validate",
        json=payload,
        headers={"Authorization": f"Bearer {responder_token}"},
    )
    assert val_resp.status_code == 403


def test_learning_tenant_isolation_and_retrieval(client, seed_data) -> None:
    org1 = seed_data["org1"]
    org2 = seed_data["org2"]
    commander1 = seed_data["commander"]
    commander2 = seed_data["other_commander"]

    token1 = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander1.subject)
    token2 = generate_jwt(organization_id=org2.id, role=UserRole.INCIDENT_COMMANDER, subject=commander2.subject)

    # Org1 creates and resolves incident
    inc1 = client.post(
        "/v1/incidents",
        json={"title": "Org1 Secret Architecture Failure", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    client.patch(f"/v1/incidents/{inc1['id']}/status", json={"status": "resolved"}, headers={"Authorization": f"Bearer {token1}"})

    # Org1 validates outcome
    client.post(
        f"/v1/incidents/{inc1['id']}/learnings/validate",
        json={
            "summary": "Org1 secret microservice database connection timeout.",
            "root_cause": "Connection pool size capped at 10.",
            "effective_remediation": "Increased pool size to 100.",
            "tags": ["database", "pool"],
        },
        headers={"Authorization": f"Bearer {token1}"},
    )

    # Org2 searches knowledge base -> Should receive 0 records (tenant isolated)
    org2_search = client.get("/v1/learnings", headers={"Authorization": f"Bearer {token2}"})
    assert org2_search.status_code == 200
    assert len(org2_search.json()) == 0

    # Org1 searches knowledge base -> Receives 1 record
    org1_search = client.get("/v1/learnings?query=database", headers={"Authorization": f"Bearer {token1}"})
    assert org1_search.status_code == 200
    assert len(org1_search.json()) == 1

    # Org1 creates a second incident and fetches relevant historical context
    inc2 = client.post(
        "/v1/incidents",
        json={"title": "Org1 New Outage", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token1}"},
    ).json()

    context_resp = client.get(
        f"/v1/incidents/{inc2['id']}/learnings/relevant",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert context_resp.status_code == 200
    context_list = context_resp.json()
    assert len(context_list) == 1
    assert "HISTORICAL REFERENCE ONLY" in context_list[0]["disclaimer"]
    assert context_list[0]["verified_root_cause"] == "Connection pool size capped at 10."
