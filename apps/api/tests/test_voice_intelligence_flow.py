"""End-to-end test verifying the Voice Room and Voice-to-AI Intelligence pipeline."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_voice_room_join_and_agora_token(client):
    # 1. Authenticate as Incident Commander
    auth_resp = client.post("/v1/identity/token", json={"role": "incident_commander"})
    assert auth_resp.status_code == 200
    token = auth_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. List incidents and select active one
    inc_resp = client.get("/v1/incidents", headers=headers)
    assert inc_resp.status_code == 200
    incidents = inc_resp.json()
    assert len(incidents) >= 1
    incident_id = incidents[0]["id"]

    # 3. Join voice room (Agora RTC token generation + presence)
    join_resp = client.post(f"/v1/incidents/{incident_id}/room/join", headers=headers)
    assert join_resp.status_code == 200
    room_data = join_resp.json()
    assert room_data["channel_name"] == f"incident-{incident_id}"
    assert room_data["is_publisher"] is True
    assert "token" in room_data
    assert len(room_data["token"]) > 20

    # 4. Check presence
    presence_resp = client.get(f"/v1/incidents/{incident_id}/room/presence", headers=headers)
    assert presence_resp.status_code == 200
    participants = presence_resp.json()
    assert any(p["presence_state"] == "joined" for p in participants)


def test_voice_statement_ai_intelligence_pipeline(client):
    # 1. Authenticate
    auth_resp = client.post("/v1/identity/token", json={"role": "incident_commander"})
    assert auth_resp.status_code == 200
    token = auth_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    inc_resp = client.get("/v1/incidents", headers=headers)
    incident_id = inc_resp.json()[0]["id"]

    # 2. Ingest statement: "We have a critical payment outage. Payment failures are increasing."
    statement_payload = {
        "messages": [
            {
                "speaker": "Alice (Commander)",
                "text": "We have a critical payment outage. Payment failures are increasing.",
                "source_type": "voice_transcript",
                "timestamp": "2026-09-01T17:45:00Z",
            }
        ]
    }

    ai_resp = client.post(
        f"/v1/incidents/{incident_id}/intelligence/analyze",
        json=statement_payload,
        headers=headers,
    )
    assert ai_resp.status_code == 200
    intelligence = ai_resp.json()

    # 3. Verify extracted facts and AI summary
    assert len(intelligence["facts"]) >= 1
    assert any("payment" in f["statement"].lower() or "outage" in f["statement"].lower() for f in intelligence["facts"])
    assert intelligence["summary"] != ""
    assert "payment outage" in intelligence["summary"].lower()

    # 4. Verify timeline events
    assert len(intelligence["timeline_events"]) >= 1
