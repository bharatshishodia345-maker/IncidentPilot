from __future__ import annotations

from tests.conftest import generate_jwt
from app.db.models import UserRole


def test_room_join_leave_and_presence_lifecycle(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    responder = seed_data["responder"]

    commander_token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)
    responder_token = generate_jwt(organization_id=org1.id, role=UserRole.RESPONDER, subject=responder.subject)

    # 1. Declare incident
    create_resp = client.post(
        "/v1/incidents",
        json={"title": "Room Voice Outage Test", "severity": "sev1"},
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert create_resp.status_code == 201
    incident_id = create_resp.json()["id"]

    # 2. Responder joins live room
    join_resp = client.post(
        f"/v1/incidents/{incident_id}/room/join",
        headers={"Authorization": f"Bearer {responder_token}"},
    )
    assert join_resp.status_code == 200
    join_data = join_resp.json()
    assert join_data["token"].startswith("007")
    assert join_data["channel_name"] == f"incident-{incident_id}"
    assert join_data["is_publisher"] is True
    assert len(join_data["participants"]) >= 1

    # 3. Check presence
    presence_resp = client.get(
        f"/v1/incidents/{incident_id}/room/presence",
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert presence_resp.status_code == 200
    presence_list = presence_resp.json()
    assert any(p["user_id"] == str(responder.id) and p["presence_state"] == "joined" for p in presence_list)

    # 4. Responder leaves room
    leave_resp = client.post(
        f"/v1/incidents/{incident_id}/room/leave",
        headers={"Authorization": f"Bearer {responder_token}"},
    )
    assert leave_resp.status_code == 200
    assert leave_resp.json()["status"] == "left"

    # 5. Check presence updated to left
    presence_after = client.get(
        f"/v1/incidents/{incident_id}/room/presence",
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert presence_after.status_code == 200
    resp_participant = next(p for p in presence_after.json() if p["user_id"] == str(responder.id))
    assert resp_participant["presence_state"] == "left"
    assert resp_participant["left_at"] is not None


def test_room_cross_tenant_isolation(client, seed_data) -> None:
    org1 = seed_data["org1"]
    org2 = seed_data["org2"]
    commander1 = seed_data["commander"]
    commander2 = seed_data["other_commander"]

    token1 = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander1.subject)
    token2 = generate_jwt(organization_id=org2.id, role=UserRole.INCIDENT_COMMANDER, subject=commander2.subject)

    # Create incident in org1
    create_resp = client.post(
        "/v1/incidents",
        json={"title": "Org1 Private Voice Room", "severity": "sev2"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    incident_id = create_resp.json()["id"]

    # Commander from org2 attempts to join org1's room -> 404 Not Found
    join_resp = client.post(
        f"/v1/incidents/{incident_id}/room/join",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert join_resp.status_code == 404
    assert join_resp.json()["code"] == "NOT_FOUND"
