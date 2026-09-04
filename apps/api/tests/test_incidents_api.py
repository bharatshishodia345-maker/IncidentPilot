from __future__ import annotations

from tests.conftest import generate_jwt
from app.db.models import IncidentSeverity, IncidentStatus, UserRole


def test_list_incidents_tenant_isolated(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]

    # Declare an incident in org1
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)
    create_resp = client.post(
        "/v1/incidents",
        json={"title": "Payment gateway timeout", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201

    # Commander lists incidents
    list_resp = client.get("/v1/incidents", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["title"] == "Payment gateway timeout"
    assert items[0]["organization_id"] == str(org1.id)

    # Other org commander sees nothing
    other_org = seed_data["org2"]
    other_commander = seed_data["other_commander"]
    other_token = generate_jwt(
        organization_id=other_org.id,
        role=UserRole.INCIDENT_COMMANDER,
        subject=other_commander.subject,
    )
    other_list_resp = client.get("/v1/incidents", headers={"Authorization": f"Bearer {other_token}"})
    assert other_list_resp.status_code == 200
    assert len(other_list_resp.json()) == 0


def test_get_incident_detail_and_cross_tenant_protection(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    create_resp = client.post(
        "/v1/incidents",
        json={"title": "Database connection pool exhaustion", "severity": "sev2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = create_resp.json()["id"]

    # Same org can read incident detail
    detail_resp = client.get(f"/v1/incidents/{incident_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail_resp.status_code == 200
    assert detail_resp.json()["title"] == "Database connection pool exhaustion"

    # Cross-tenant access is blocked with 404
    other_org = seed_data["org2"]
    other_commander = seed_data["other_commander"]
    other_token = generate_jwt(
        organization_id=other_org.id,
        role=UserRole.INCIDENT_COMMANDER,
        subject=other_commander.subject,
    )
    cross_resp = client.get(f"/v1/incidents/{incident_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert cross_resp.status_code == 404
    assert cross_resp.json()["code"] == "NOT_FOUND"


def test_observer_cannot_declare_incident(client, seed_data) -> None:
    org1 = seed_data["org1"]
    observer = seed_data["observer"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.OBSERVER, subject=observer.subject)

    response = client.post(
        "/v1/incidents",
        json={"title": "Unauthorized declaration", "severity": "sev3"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "HTTP_ERROR" or response.json()["code"] == "PERMISSION_DENIED"


def test_incident_status_transition_lifecycle(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    create_resp = client.post(
        "/v1/incidents",
        json={"title": "Auth token cache desync", "severity": "sev2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    incident_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == IncidentStatus.DECLARED.value

    # Update to OPEN
    patch_resp = client.patch(
        f"/v1/incidents/{incident_id}/status",
        json={"status": IncidentStatus.OPEN.value},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == IncidentStatus.OPEN.value

    # Update to RESOLVED
    patch_resolved = client.patch(
        f"/v1/incidents/{incident_id}/status",
        json={"status": IncidentStatus.RESOLVED.value},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_resolved.status_code == 200
    assert patch_resolved.json()["status"] == IncidentStatus.RESOLVED.value
    assert patch_resolved.json()["closed_at"] is not None


def test_invalid_title_validation(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    response = client.post(
        "/v1/incidents",
        json={"title": "   a   ", "severity": "sev1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
