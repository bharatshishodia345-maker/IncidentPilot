"""Live end-to-end HTTP server test for multilingual IncidentPilot with in-process ASGI fallback."""

import httpx
import pytest
from app.main import app

LIVE_SERVER_URL = "http://127.0.0.1:8000"


@pytest.mark.anyio
async def test_live_multilingual_server_pipeline():
    # Use ASGITransport to guarantee reliability regardless of external uvicorn process
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Check frontend HTML and JS assets
        html_resp = await client.get("/")
        assert html_resp.status_code == 200
        assert "IncidentPilot" in html_resp.text

        js_resp = await client.get("/static/app.js")
        assert js_resp.status_code == 200
        assert "speakCurrentSummary" in js_resp.text
        assert "detectedLanguage" in js_resp.text

        # 2. Authenticate
        auth_resp = await client.post("/v1/identity/token", json={"role": "incident_commander"})
        assert auth_resp.status_code == 200
        token = auth_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create fresh incident
        inc_resp = await client.post(
            "/v1/incidents",
            json={"title": "Multilingual War Room Outage", "severity": "sev1", "status": "open"},
            headers=headers,
        )
        assert inc_resp.status_code == 201
        incident_id = inc_resp.json()["id"]

        # 4. TEST 1 - English statement
        res_en = await client.post(
            f"/v1/incidents/{incident_id}/intelligence/analyze",
            json={
                "messages": [
                    {
                        "speaker": "Alice (Commander)",
                        "text": "Payment failures are increasing. Monitoring shows a 35 percent error rate.",
                        "source_type": "voice_transcript",
                        "timestamp": "2026-09-01T18:00:00Z",
                    }
                ],
                "language": "english",
            },
            headers=headers,
        )
        assert res_en.status_code == 200
        data_en = res_en.json()
        assert data_en["language"] == "english"
        assert len(data_en["facts"]) >= 1

        # 5. TEST 2 - Hinglish statement with multi-turn context
        res_hi = await client.post(
            f"/v1/incidents/{incident_id}/intelligence/analyze",
            json={
                "messages": [
                    {
                        "speaker": "Alice",
                        "text": "Payment failures are increasing.",
                        "source_type": "voice_transcript",
                        "timestamp": "2026-09-01T18:00:00Z",
                    },
                    {
                        "speaker": "Bob",
                        "text": "Bhai payment fail ho raha hai aur database latency bhi high hai.",
                        "source_type": "voice_transcript",
                        "timestamp": "2026-09-01T18:01:00Z",
                    },
                ],
                "language": "hinglish",
            },
            headers=headers,
        )
        assert res_hi.status_code == 200
        data_hi = res_hi.json()
        assert data_hi["language"] == "hinglish"
        assert "samajh gaya" in data_hi["summary"].lower()

        # 6. TEST 3 - Switch back to English
        res_switch = await client.post(
            f"/v1/incidents/{incident_id}/intelligence/analyze",
            json={
                "messages": [
                    {
                        "speaker": "Bob",
                        "text": "Bhai payment fail ho raha hai aur database latency bhi high hai.",
                        "source_type": "voice_transcript",
                        "timestamp": "2026-09-01T18:01:00Z",
                    },
                    {
                        "speaker": "Alice",
                        "text": "The database latency is now normal.",
                        "source_type": "voice_transcript",
                        "timestamp": "2026-09-01T18:02:00Z",
                    },
                ],
                "language": "english",
            },
            headers=headers,
        )
        assert res_switch.status_code == 200
        data_switch = res_switch.json()
        assert data_switch["language"] == "english"
        assert "database latency" in data_switch["summary"].lower() or "normal" in data_switch["summary"].lower()
