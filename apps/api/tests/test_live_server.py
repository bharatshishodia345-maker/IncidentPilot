"""End-to-end live server validation script with in-process TestClient fallback."""

from __future__ import annotations

import json
import socket
from fastapi.testclient import TestClient

from app.main import app


def is_live_port_open(host: str = "127.0.0.1", port: int = 8000) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.1)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def test_live_server():
    client = TestClient(app)
    live_active = is_live_port_open()

    def req(path: str, method: str = "GET", data: dict | None = None, headers: dict | None = None) -> tuple[int, dict | str]:
        if live_active:
            try:
                import urllib.request
                url = f"http://127.0.0.1:8000{path}"
                h = dict(headers or {})
                body = json.dumps(data).encode("utf-8") if data else None
                if body and "Content-Type" not in h:
                    h["Content-Type"] = "application/json"
                request = urllib.request.Request(url, data=body, headers=h, method=method)
                with urllib.request.urlopen(request, timeout=2.0) as resp:
                    content = resp.read().decode("utf-8")
                    try:
                        return resp.status, json.loads(content)
                    except Exception:
                        return resp.status, content
            except Exception:
                pass

        resp = client.request(method=method, url=path, json=data, headers=headers)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, resp.text

    # 1. Health check
    status, body = req("/health")
    assert status == 200
    assert isinstance(body, dict)
    assert body["status"] == "ok"
    assert body["database"] == "ok"

    # 2. Frontend HTML
    status, html = req("/")
    assert status == 200
    assert "IncidentPilot" in str(html)
    assert "Agora Live Voice Room" in str(html)

    # 3. Static assets
    status, js = req("/static/app.js")
    assert status == 200
    assert "authenticatePersona" in str(js)

    status, css = req("/static/styles.css")
    assert status == 200
    assert "--bg-main" in str(css)

    # 4. Identity & Token
    status, token_resp = req("/v1/identity/token", method="POST", data={"role": "incident_commander"})
    assert status == 200
    token = token_resp["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 5. Create Fresh Incident for Test Run
    status, created_inc = req(
        "/v1/incidents",
        method="POST",
        headers=auth_headers,
        data={
            "title": "Payment Authorization Failure Spike (Live Test)",
            "severity": "sev1",
            "status": "open",
        },
    )
    assert status == 201
    incident_id = created_inc["id"]

    # 6. Incident Details & Timeline
    status, inc_detail = req(f"/v1/incidents/{incident_id}", headers=auth_headers)
    assert status == 200
    assert inc_detail["id"] == incident_id

    # 7. Agora Voice Room Join
    status, room = req(f"/v1/incidents/{incident_id}/room/join", method="POST", headers=auth_headers)
    assert status == 200
    assert room["channel_name"] == f"incident-{incident_id}"
    assert "token" in room
    assert len(room["token"]) > 20

    # 8. Room Presence
    status, presence = req(f"/v1/incidents/{incident_id}/room/presence", headers=auth_headers)
    assert status == 200
    assert any(p["presence_state"] == "joined" for p in presence)

    # 9. Payment Outage Intelligence Demo
    status, intel = req(f"/v1/incidents/{incident_id}/intelligence/payment-demo", headers=auth_headers)
    assert status == 200
    assert len(intel["facts"]) >= 2
    assert len(intel["hypotheses"]) >= 1
    assert len(intel["conflicts"]) >= 1
    assert len(intel["unknowns"]) >= 1
    assert len(intel["actions"]) >= 1
    assert len(intel["summary"]) > 0

    # 10. Allowlisted Action Proposal & Commander Approval Gate
    status, proposal = req(
        f"/v1/incidents/{incident_id}/actions/propose",
        method="POST",
        headers=auth_headers,
        data={
            "action_type": "rollback_deployment",
            "title": "Rollback canary release to v2.13.9",
            "description": "Authorized canary rollback to stabilize checkout error rate",
            "risk_level": "high",
            "parameters": {
                "service_name": "checkout-service",
                "target_version": "v2.13.9",
                "cluster": "production-primary",
            },
        },
    )
    assert status == 201
    prop_id = proposal["id"]

    # Commander authorization
    status, approved = req(
        f"/v1/incidents/{incident_id}/actions/proposals/{prop_id}/approve",
        method="POST",
        headers=auth_headers,
        data={"rationale": "High 503 error spike confirmed in war room"},
    )
    assert status == 200
    assert approved["status"] == "executed"
    assert approved["execution_result"]["status"] == "success"

    # 11. Status Transition
    status, updated_inc = req(
        f"/v1/incidents/{incident_id}/status",
        method="PATCH",
        headers=auth_headers,
        data={"status": "mitigated"},
    )
    assert status == 200
    assert updated_inc["status"] == "mitigated"

    # 12. Learning Outcome Validation
    status, learning_record = req(
        f"/v1/incidents/{incident_id}/learnings/validate",
        method="POST",
        headers=auth_headers,
        data={
            "summary": "Canary deployment v2.14 introduced 503 errors on European checkout routes.",
            "root_cause": "Canary release v2.14 contained breaking schema changes causing database connection pool saturation.",
            "effective_remediation": "Rollback canary deployment to v2.13.9 stabilized error rate.",
            "preventative_actions": ["Add synthetic pre-deployment gateway canary health checks"],
            "tags": ["canary", "payments", "rollback"],
        },
    )
    assert status == 201
    assert learning_record["incident_id"] == incident_id

    # 13. Relevant Historical Learning Context & Knowledge Base Search
    status, kb_records = req(f"/v1/learnings?query=canary", headers=auth_headers)
    assert status == 200
    assert len(kb_records) >= 1
    assert kb_records[0]["incident_id"] == incident_id

    # 14. Integrations
    status, providers = req("/v1/integrations/providers")
    assert status == 200
    assert len(providers) >= 3

    status, slack_res = req(
        f"/v1/incidents/{incident_id}/integrations/slack/broadcast",
        method="POST",
        headers=auth_headers,
        data={
            "channel": "#incident-war-room",
            "title": "SEV1 Payment Outage Mitigated",
            "text": "Incident mitigated successfully via canary rollback.",
            "severity": "sev1",
            "status": "mitigated",
        },
    )
    assert status == 200
    assert slack_res["ok"] is True

    status, jira_res = req(
        f"/v1/incidents/{incident_id}/integrations/jira/ticket",
        method="POST",
        headers=auth_headers,
        data={
            "project_key": "PAY",
            "summary": "Payment Outage Post-Mortem",
            "description": "Investigate root cause of 503 errors during canary v2.14 deploy.",
            "priority": "Highest",
            "issue_type": "Incident",
        },
    )
    assert status == 201
    assert "issue_key" in jira_res

    status, metrics = req(
        f"/v1/incidents/{incident_id}/integrations/monitoring/metrics?service_name=checkout-service",
        headers=auth_headers,
    )
    assert status == 200
    assert metrics["service_name"] == "checkout-service"


if __name__ == "__main__":
    test_live_server()
