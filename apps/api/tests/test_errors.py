from __future__ import annotations

from tests.conftest import generate_jwt
from app.db.models import UserRole


def test_correlation_id_in_response_headers(client) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "custom-req-id-123"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "custom-req-id-123"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"



def test_404_error_response_format(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    response = client.get(
        "/v1/incidents/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "NOT_FOUND"
    assert "detail" in data


def test_422_validation_error_format(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)

    response = client.post(
        "/v1/incidents",
        json={"title": "ok", "severity": "invalid_sev"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "errors" in data
    assert isinstance(data["errors"], list)
