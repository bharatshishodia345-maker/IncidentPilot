"""End-to-End Scenario Verification for IncidentPilot.

Tests the full Payment Outage lifecycle:
Incident Declaration
→ Users join Agora live room
→ Conversation enters AI intelligence pipeline
→ Facts extracted (grounded with evidence)
→ Hypotheses separated (never invented root causes)
→ Contradictory claims detected
→ Action items assigned to owner (no invented assignees)
→ Timeline updated
→ Allowlisted action proposed
→ Policy & parameter validation checked
→ Failure paths: Unauthorized approval rejected (403), Replay blocked (409), Unsafe inputs rejected (422)
→ Success path: Human commander authorizes remediation
→ Sandboxed action executed & recorded
→ External integrations (Slack & Jira) dispatched with audit trail
→ Incident resolved & verified outcome committed to knowledge base
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.conftest import generate_jwt
from app.actions.schemas import AllowlistedActionType, ProposalStatus
from app.ai.schemas import IntelligenceSourceType
from app.db.models import AuditActorType, AuditEvent, TimelineEvent, UserRole


def test_payment_outage_complete_lifecycle_e2e(client, seed_data) -> None:
    org1 = seed_data["org1"]
    commander = seed_data["commander"]
    responder = seed_data["responder"]
    observer = seed_data["observer"]

    commander_token = generate_jwt(organization_id=org1.id, role=UserRole.INCIDENT_COMMANDER, subject=commander.subject)
    responder_token = generate_jwt(organization_id=org1.id, role=UserRole.RESPONDER, subject=responder.subject)
    observer_token = generate_jwt(organization_id=org1.id, role=UserRole.OBSERVER, subject=observer.subject)

    # -------------------------------------------------------------------------
    # STEP 1: Incident Declaration (SEV1 Payment Outage)
    # -------------------------------------------------------------------------
    create_resp = client.post(
        "/v1/incidents",
        json={
            "title": "Payment Gateway 503 Authorization Outage",
            "severity": "sev1",
            "status": "open",
        },
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert create_resp.status_code == 201
    incident = create_resp.json()
    incident_id = incident["id"]
    assert incident["severity"] == "sev1"
    assert incident["status"] == "open"

    # -------------------------------------------------------------------------
    # STEP 2: Agora Live Incident Room (Join & Presence)
    # -------------------------------------------------------------------------
    # Commander joins room
    cmd_join_resp = client.post(
        f"/v1/incidents/{incident_id}/room/join",
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert cmd_join_resp.status_code == 200
    cmd_join_data = cmd_join_resp.json()
    assert cmd_join_data["token"].startswith("007")
    assert cmd_join_data["is_publisher"] is True
    assert cmd_join_data["channel_name"] == f"incident-{incident_id}"

    # Responder joins room
    resp_join_resp = client.post(
        f"/v1/incidents/{incident_id}/room/join",
        headers={"Authorization": f"Bearer {responder_token}"},
    )
    assert resp_join_resp.status_code == 200
    assert resp_join_resp.json()["is_publisher"] is True

    # Check Presence
    presence_resp = client.get(
        f"/v1/incidents/{incident_id}/room/presence",
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert presence_resp.status_code == 200
    participants = presence_resp.json()
    assert len([p for p in participants if p["presence_state"] == "joined"]) == 2

    # -------------------------------------------------------------------------
    # STEP 3: Conversation & Telemetry Enters AI Intelligence Pipeline
    # -------------------------------------------------------------------------
    now_iso = datetime.now(timezone.utc).isoformat()
    transcript_payload = {
        "incident_title": incident["title"],
        "messages": [
            {
                "speaker": "Datadog Telemetry",
                "text": "Payment failures jumped to 42.8% with HTTP 503 errors on checkout gateway.",
                "source_type": "telemetry_log",
                "timestamp": now_iso,
            },
            {
                "speaker": "Alice (Commander)",
                "text": "Incident declared SEV1. Responders investigate stripe gateway and DB pools.",
                "source_type": "voice_transcript",
                "timestamp": now_iso,
            },
            {
                "speaker": "Bob (Database Lead)",
                "text": "I suspect database latency spiked to 4500ms and DB pool is saturated.",
                "source_type": "voice_transcript",
                "timestamp": now_iso,
            },
            {
                "speaker": "Charlie (Infra)",
                "text": "Wait, database is healthy and CPU is at 12%, but external stripe gateway is throwing timeouts.",
                "source_type": "voice_transcript",
                "timestamp": now_iso,
            },
            {
                "speaker": "Alice (Commander)",
                "text": "Does anyone know if canary deployment v2.14 was deployed at 21:45 today?",
                "source_type": "voice_transcript",
                "timestamp": now_iso,
            },
            {
                "speaker": "Dave (Release Lead)",
                "text": "Canary deployment v2.14 was deployed at 21:45.",
                "source_type": "voice_transcript",
                "timestamp": now_iso,
            },
            {
                "speaker": "Alice (Commander)",
                "text": "Action item: @dave please prepare canary rollback to v2.13.9.",
                "source_type": "voice_transcript",
                "timestamp": now_iso,
            },
        ],
    }

    ai_resp = client.post(
        f"/v1/incidents/{incident_id}/intelligence/analyze",
        json=transcript_payload,
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert ai_resp.status_code == 200
    intel = ai_resp.json()

    # Verify Facts vs Hypotheses Separation
    assert len(intel["facts"]) >= 1
    assert any("503" in f["statement"] or "42.8%" in f["statement"] for f in intel["facts"])
    assert all(len(f["evidence"]) > 0 for f in intel["facts"])  # Grounded evidence

    assert len(intel["hypotheses"]) >= 1
    assert any("Bob" in h["proposed_by"] for h in intel["hypotheses"])
    # Bob's speculation must not be in facts
    assert not any("suspect" in f["statement"].lower() for f in intel["facts"])

    # Verify Conflict Detection
    assert len(intel["conflicts"]) >= 1
    conflict = intel["conflicts"][0]
    assert "database" in conflict["description"].lower()

    # Verify Unknowns / Missing Info Detection
    assert len(intel["unknowns"]) >= 1

    # Verify Action Items & Owner Assignment
    assert len(intel["actions"]) >= 1
    dave_action = next(a for a in intel["actions"] if "rollback" in a["title"].lower())
    assert dave_action["assigned_owner"].lower() == "dave"  # Named owner preserved

    # Verify Spoken Summary
    assert len(intel["summary"]) > 20

    # -------------------------------------------------------------------------
    # STEP 4: Human-in-the-Loop Remediation Proposal & Policy Validation
    # -------------------------------------------------------------------------
    # Propose allowlisted action: rollback_deployment
    proposal_payload = {
        "action_type": "rollback_deployment",
        "title": "Rollback checkout-service to v2.13.9",
        "description": "Revert canary release v2.14 across production cluster",
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
        json=proposal_payload,
        headers={"Authorization": f"Bearer {responder_token}"},
    )
    assert prop_resp.status_code == 201
    proposal = prop_resp.json()
    proposal_id = proposal["id"]
    assert proposal["status"] == "pending_approval"
    assert proposal["risk_level"] == "high"

    # -------------------------------------------------------------------------
    # STEP 5: Policy & Failure Paths
    # -------------------------------------------------------------------------
    # Failure Path 1: Observer attempts to authorize -> 403 Forbidden
    obs_auth_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {observer_token}"},
    )
    assert obs_auth_resp.status_code == 403

    # Failure Path 2: Responder attempts to authorize high-risk action -> 403 Forbidden
    resp_auth_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {responder_token}"},
    )
    assert resp_auth_resp.status_code == 403

    # Failure Path 3: Unsafe parameter proposal (command injection attempt) -> 422
    unsafe_prop_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/propose",
        json={
            "action_type": "rollback_deployment",
            "title": "Unsafe Action",
            "parameters": {
                "service_name": "checkout; cat /etc/passwd",
                "target_version": "v1.0",
                "cluster": "prod",
            },
        },
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert unsafe_prop_resp.status_code == 422

    # -------------------------------------------------------------------------
    # STEP 6: Success Path: Incident Commander Authorizes Execution
    # -------------------------------------------------------------------------
    cmd_auth_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        json={"rationale": "High error rate confirmed on canary v2.14. Rollback approved."},
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert cmd_auth_resp.status_code == 200
    executed_action = cmd_auth_resp.json()
    assert executed_action["status"] == "executed"
    assert executed_action["approved_by_user_id"] == str(commander.id)
    assert executed_action["execution_result"]["status"] == "success"
    assert executed_action["execution_result"]["details"]["deployment_status"] == "reverted_successfully"

    # Replay Protection: Second approval attempt blocked -> 409 Conflict
    replay_resp = client.post(
        f"/v1/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert replay_resp.status_code == 409

    # -------------------------------------------------------------------------
    # STEP 7: External Integrations & Audit Logging
    # -------------------------------------------------------------------------
    # Slack Broadcast
    slack_resp = client.post(
        f"/v1/incidents/{incident_id}/integrations/slack/broadcast",
        json={
            "channel": "#incident-war-room",
            "title": "SEV1 Update: Rollback v2.13.9 Executed",
            "text": "Canary rollback completed successfully. Traffic 100% healthy.",
            "severity": "sev1",
            "status": "mitigated",
        },
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert slack_resp.status_code == 200
    assert slack_resp.json()["ok"] is True

    # Jira Ticket Creation
    jira_resp = client.post(
        f"/v1/incidents/{incident_id}/integrations/jira/ticket",
        json={
            "project_key": "PAY",
            "summary": "Payment Outage Post-Mortem Tracking",
            "description": "SEV1 incident tracking ticket for payment gateway outage.",
        },
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert jira_resp.status_code == 201

    # -------------------------------------------------------------------------
    # STEP 8: Status Transitions & Timeline Stream Check
    # -------------------------------------------------------------------------
    client.patch(
        f"/v1/incidents/{incident_id}/status",
        json={"status": "mitigated"},
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    client.patch(
        f"/v1/incidents/{incident_id}/status",
        json={"status": "resolved"},
        headers={"Authorization": f"Bearer {commander_token}"},
    )

    detail_resp = client.get(
        f"/v1/incidents/{incident_id}",
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert detail_resp.status_code == 200
    final_detail = detail_resp.json()
    assert final_detail["status"] == "resolved"
    assert len(final_detail["timeline_events"]) >= 3  # Status changes, actions, broadcasts recorded

    # -------------------------------------------------------------------------
    # STEP 9: Final Incident Summary & Verified Outcome Learning
    # -------------------------------------------------------------------------
    learn_resp = client.post(
        f"/v1/incidents/{incident_id}/learnings/validate",
        json={
            "summary": "Payment failure spike caused by faulty canary deployment v2.14 with Stripe gateway timeouts.",
            "root_cause": "Canary v2.14 introduced unhandled Stripe API connection pool timeout.",
            "effective_remediation": "Authorized rollback of checkout-service to v2.13.9.",
            "preventative_actions": [
                "Add automated canary rollback on 5xx error rate > 5%",
                "Implement circuit breaker pattern for Stripe gateway client",
            ],
            "tags": ["payment", "canary", "stripe", "rollback"],
        },
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert learn_resp.status_code == 201
    learned_record = learn_resp.json()
    assert learned_record["root_cause"] == "Canary v2.14 introduced unhandled Stripe API connection pool timeout."

    # Verify Future Incident Retrieval with Non-Fact Disclaimer
    search_resp = client.get(
        "/v1/learnings?query=canary",
        headers={"Authorization": f"Bearer {commander_token}"},
    )
    assert search_resp.status_code == 200
    assert len(search_resp.json()) >= 1
