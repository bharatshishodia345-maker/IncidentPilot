"""Comprehensive tests for turn-aware multi-domain incident commander conversation engine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.ai.provider import (
    DeterministicIntelligenceEngine,
    detect_language,
    infer_incident_type,
)
from app.ai.schemas import (
    AnalysisRequest,
    IntelligenceSourceType,
    TranscriptMessage,
)


def _msg(speaker: str, text: str) -> TranscriptMessage:
    return TranscriptMessage(
        speaker=speaker,
        text=text,
        timestamp=datetime.now(timezone.utc),
        source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
    )


def _req(*texts: tuple[str, str], turn: int = 1, language: str | None = None) -> AnalysisRequest:
    return AnalysisRequest(
        messages=[_msg(spk, txt) for spk, txt in texts],
        conversation_turn=turn,
        language=language,
    )


ENGINE = DeterministicIntelligenceEngine()


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

class TestLanguageDetection:
    def test_english_detected(self):
        assert detect_language("Payment failures are increasing.") == "english"

    def test_hindi_devanagari(self):
        assert detect_language("पेमेंट फेल हो रहे हैं।") == "hindi"

    def test_hinglish_detected_strong(self):
        assert detect_language("Payment fail ho raha hai bhai.") == "hinglish"

    def test_hinglish_roman(self):
        assert detect_language("Database mein kuch issue hai, latency badh rahi hai.") == "hinglish"

    def test_empty_falls_back_to_previous(self):
        assert detect_language("", previous_language="hindi") == "hindi"

    def test_english_technical_only(self):
        result = detect_language("Database CPU is at 95 percent now.")
        assert result == "english"


# ---------------------------------------------------------------------------
# Incident type inference
# ---------------------------------------------------------------------------

class TestIncidentTypeInference:
    def test_payment(self):
        assert infer_incident_type("payment failures are increasing") == "payment_service_failure"

    def test_database(self):
        assert infer_incident_type("database cpu is at 95 percent") == "database_overload"

    def test_auth(self):
        assert infer_incident_type("users cannot login sso is down") == "authentication_failure"

    def test_deployment(self):
        assert infer_incident_type("latest deployment caused issues") == "deployment_regression"

    def test_network(self):
        assert infer_incident_type("network latency is increasing between services") == "network_latency"

    def test_api(self):
        assert infer_incident_type("503 gateway timeouts are spiking") == "api_gateway_failure"

    def test_security(self):
        assert infer_incident_type("suspicious login activity detected") == "security_incident"

    def test_general_fallback(self):
        assert infer_incident_type("something is broken") == "general_technical_incident"


# ---------------------------------------------------------------------------
# 6-domain Turn 1 tests: different incident → different AI response
# ---------------------------------------------------------------------------

class TestSixDomainsTurn1:
    @pytest.mark.anyio
    async def test_payment_turn1(self):
        req = _req(("Alice", "Payment failures are increasing."), turn=1)
        result = await ENGINE.analyze(req)
        assert result.incident_type == "payment_service_failure"
        # AI must ask about error rate or timing — not repeat the problem
        assert "payment failures are increasing" not in result.summary.lower()
        assert any(w in result.summary.lower() for w in ["error rate", "when", "begin", "start", "impact", "kab", "शुरू"])

    @pytest.mark.anyio
    async def test_database_turn1(self):
        req = _req(("Bob", "Database CPU is at 95 percent."), turn=1)
        result = await ENGINE.analyze(req)
        assert result.incident_type == "database_overload"
        # AI must ask about connection pool, locking, or nodes
        assert any(w in result.summary.lower() for w in ["pool", "lock", "node", "query", "connection"])
        # Must NOT repeat the statement verbatim
        assert "database cpu is at 95 percent" not in result.summary.lower()

    @pytest.mark.anyio
    async def test_auth_turn1(self):
        req = _req(("Charlie", "Users cannot log in."), turn=1)
        result = await ENGINE.analyze(req)
        assert result.incident_type == "authentication_failure"
        assert any(w in result.summary.lower() for w in ["sso", "provider", "session", "isolated", "401", "403"])

    @pytest.mark.anyio
    async def test_deployment_turn1(self):
        req = _req(("Dave", "The latest deployment caused API timeouts."), turn=1)
        result = await ENGINE.analyze(req)
        assert result.incident_type in ("deployment_regression", "api_gateway_failure")
        assert any(w in result.summary.lower() for w in ["version", "when", "canary", "rollout", "timestamp"])

    @pytest.mark.anyio
    async def test_network_turn1(self):
        req = _req(("Eve", "Network latency between two services is increasing."), turn=1)
        result = await ENGINE.analyze(req)
        assert result.incident_type == "network_latency"
        assert any(w in result.summary.lower() for w in ["path", "link", "zone", "vpc", "route", "degraded"])

    @pytest.mark.anyio
    async def test_security_turn1(self):
        req = _req(("Alice", "We detected suspicious login activity."), turn=1)
        result = await ENGINE.analyze(req)
        assert result.incident_type == "security_incident"
        assert any(w in result.summary.lower() for w in ["access", "account", "pattern", "ip", "exfiltration"])


# ---------------------------------------------------------------------------
# Multi-turn payment outage investigation
# ---------------------------------------------------------------------------

class TestMultiTurnPaymentOutage:
    @pytest.mark.anyio
    async def test_turn1_asks_for_error_rate(self):
        req = _req(("Alice", "Payment failures are increasing."), turn=1)
        r = await ENGINE.analyze(req)
        # Turn 1 CLARIFY: ask for error rate and timing
        assert r.response_type == "CLARIFY"
        assert any(w in r.summary.lower() for w in ["error rate", "when", "impact"])
        assert r.current_goal is not None

    @pytest.mark.anyio
    async def test_turn2_asks_scope_after_error_rate_given(self):
        req = _req(
            ("Alice", "Payment failures are increasing."),
            ("Alice", "Error rate is 35 percent."),
            turn=2,
        )
        r = await ENGINE.analyze(req)
        # Turn 2 INVESTIGATE: narrow scope to regions/routes
        assert r.response_type == "INVESTIGATE"
        assert any(w in r.summary.lower() for w in ["region", "scope", "geographic", "all", "route", "checkout"])
        # Must not repeat "35 percent" as the main statement
        assert "payment failures are increasing" not in r.summary.lower()

    @pytest.mark.anyio
    async def test_turn3_asks_changes_after_scope(self):
        req = _req(
            ("Alice", "Payment failures are increasing."),
            ("Alice", "Error rate is 35 percent."),
            ("Alice", "Only Europe is affected."),
            turn=3,
        )
        r = await ENGINE.analyze(req)
        # Turn 3 INVESTIGATE: ask about recent changes
        assert r.response_type == "INVESTIGATE"
        assert any(w in r.summary.lower() for w in ["deployment", "config", "change", "update", "dependency", "deploy"])

    @pytest.mark.anyio
    async def test_turn4_correlates_deployment_evidence(self):
        req = _req(
            ("Alice", "Payment failures are increasing."),
            ("Alice", "Error rate is 35 percent."),
            ("Alice", "Only Europe is affected."),
            ("Dave", "A deployment happened 15 minutes ago."),
            turn=4,
        )
        r = await ENGINE.analyze(req)
        # Turn 4 VERIFY: correlate telemetry/timing
        assert r.response_type == "VERIFY"
        assert any(w in r.summary.lower() for w in ["gateway", "latency", "internal", "log", "correlate", "timing", "upstream"])

    @pytest.mark.anyio
    async def test_turn5_moves_to_recommendation(self):
        req = _req(
            ("Alice", "Payment failures are increasing."),
            ("Alice", "Error rate is 35 percent."),
            ("Alice", "Only Europe is affected."),
            ("Dave", "A deployment happened 15 minutes ago."),
            ("Bob", "Database latency is also high."),
            turn=5,
        )
        r = await ENGINE.analyze(req)
        # Turn 5+ should be RECOMMEND (or WARN if conflicts)
        assert r.response_type in ("RECOMMEND", "WARN", "VERIFY")
        # Should include facts from the conversation
        assert len(r.facts) > 0

    @pytest.mark.anyio
    async def test_all_5_turns_produce_different_responses(self):
        """Core test: no two consecutive turns should produce the same summary."""
        histories = [
            [("Alice", "Payment failures are increasing.")],
            [("Alice", "Payment failures are increasing."), ("Alice", "Error rate is 35 percent.")],
            [("Alice", "Payment failures are increasing."), ("Alice", "Error rate is 35 percent."), ("Alice", "Only Europe is affected.")],
            [("Alice", "Payment failures are increasing."), ("Alice", "Error rate is 35 percent."), ("Alice", "Only Europe is affected."), ("Dave", "A deployment happened 15 minutes ago.")],
            [("Alice", "Payment failures are increasing."), ("Alice", "Error rate is 35 percent."), ("Alice", "Only Europe is affected."), ("Dave", "A deployment happened 15 minutes ago."), ("Bob", "Database latency is also high.")],
        ]
        summaries = []
        for turn_idx, history in enumerate(histories, start=1):
            req = _req(*history, turn=turn_idx)
            r = await ENGINE.analyze(req)
            summaries.append(r.summary.lower()[:80])  # First 80 chars as fingerprint

        # All summaries should be distinct
        assert len(set(summaries)) == len(summaries), (
            f"Duplicate summaries detected across turns: {summaries}"
        )


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

class TestConflictDetection:
    @pytest.mark.anyio
    async def test_db_health_conflict(self):
        req = _req(
            ("Bob", "Database latency spiked to 4500ms and DB pool saturated."),
            ("Charlie", "Database is healthy and database CPU is at 12%."),
            turn=2,
        )
        r = await ENGINE.analyze(req)
        assert len(r.conflicts) > 0
        assert r.response_type == "WARN"
        assert "conflict" in r.summary.lower() or "contradict" in r.summary.lower() or "conflicting" in r.summary.lower()

    @pytest.mark.anyio
    async def test_conflict_overrides_normal_turn(self):
        """Conflict must take priority over normal turn-based investigation."""
        req = _req(
            ("Bob", "Database latency spiked to 4500ms."),
            ("Charlie", "Database is healthy and database CPU is at 12%."),
            ("Alice", "Payment failures are increasing."),
            turn=3,
        )
        r = await ENGINE.analyze(req)
        # Conflict must surface even at turn 3
        assert r.response_type == "WARN"
        assert len(r.conflicts) > 0


# ---------------------------------------------------------------------------
# Fact vs hypothesis separation
# ---------------------------------------------------------------------------

class TestFactHypothesisSeparation:
    @pytest.mark.anyio
    async def test_speculative_message_becomes_hypothesis(self):
        req = _req(("Bob", "Maybe the database is causing the issue."), turn=1)
        r = await ENGINE.analyze(req)
        assert len(r.hypotheses) > 0
        assert r.response_type == "VERIFY"
        # AI should ask how to verify — not assert the hypothesis as fact
        assert any(w in r.summary.lower() for w in ["verify", "confirm", "metric", "log", "refute"])

    @pytest.mark.anyio
    async def test_metric_becomes_fact(self):
        req = _req(("Alice", "Error rate is at 42 percent."), turn=1)
        r = await ENGINE.analyze(req)
        assert len(r.facts) > 0
        assert r.facts[0].confidence > 0


# ---------------------------------------------------------------------------
# Recovery / resolution
# ---------------------------------------------------------------------------

class TestRecoveryDetection:
    @pytest.mark.anyio
    async def test_recovery_detected(self):
        req = _req(
            ("Alice", "Payment failures are increasing."),
            ("Alice", "Error rate is 35 percent."),
            ("Alice", "Payment failures are back to normal and monitoring confirms recovery."),
            turn=3,
        )
        r = await ENGINE.analyze(req)
        assert r.response_type == "CONFIRM"
        assert r.resolution_state in ("RECOVERING", "RESOLVED")
        assert any(w in r.summary.lower() for w in ["recover", "resolv", "close", "post-mortem", "normal"])


# ---------------------------------------------------------------------------
# Hindi and Hinglish language responses
# ---------------------------------------------------------------------------

class TestMultilingualResponses:
    @pytest.mark.anyio
    async def test_hindi_response(self):
        req = _req(
            ("Alice", "पेमेंट फेल हो रहे हैं और error बढ़ रहा है।"),
            turn=1,
        )
        r = await ENGINE.analyze(req)
        assert r.language == "hindi"
        # Response should contain Hindi characters or words
        assert re.search(r"[\u0900-\u097F]", r.summary) or any(
            w in r.summary.lower() for w in ["error", "impact", "verify", "rate"]
        )

    @pytest.mark.anyio
    async def test_hinglish_response(self):
        req = _req(
            ("Alice", "Payment fail ho raha hai bhai, error rate badh raha hai."),
            turn=1,
        )
        r = await ENGINE.analyze(req)
        assert r.language == "hinglish"
        # Hinglish response should use Roman-script Hindi markers
        assert any(w in r.summary.lower() for w in ["kya", "regions", "error", "verify", "ho", "hai", "rate"])

    @pytest.mark.anyio
    async def test_english_response(self):
        req = _req(("Alice", "Payment failures are increasing."), turn=1)
        r = await ENGINE.analyze(req)
        assert r.language == "english"
        assert any(w in r.summary.lower() for w in ["error rate", "when", "impact", "failures"])

    @pytest.mark.anyio
    async def test_hinglish_turn2(self):
        req = _req(
            ("Alice", "Payment fail ho raha hai."),
            ("Alice", "35 percent error rate aa rahi hai."),
            turn=2,
        )
        r = await ENGINE.analyze(req)
        assert r.language == "hinglish"
        # Turn 2 should ask about scope
        assert any(w in r.summary.lower() for w in ["region", "route", "scope", "affected", "sab", "limited", "sirf"])


# ---------------------------------------------------------------------------
# Human approval detection
# ---------------------------------------------------------------------------

class TestHumanApproval:
    @pytest.mark.anyio
    async def test_rollback_decision_triggers_approval(self):
        req = _req(
            ("Alice", "Payment failures are increasing."),
            ("Alice", "We decided to rollback canary deployment v2.14 immediately."),
            turn=2,
        )
        r = await ENGINE.analyze(req)
        assert r.approval_state in ("PENDING_APPROVAL", "APPROVED")
        assert r.response_type == "APPROVAL"
        assert any(w in r.summary.lower() for w in ["authorization", "confirm", "commander", "authorize", "consequential"])


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------

class TestAuditAndActions:
    @pytest.mark.anyio
    async def test_action_extracted_with_owner(self):
        req = _req(
            ("Alice", "I will investigate the checkout service logs right now."),
            turn=1,
        )
        r = await ENGINE.analyze(req)
        assert len(r.actions) > 0
        # Owner should be Alice since she said "I will"
        alice_actions = [a for a in r.actions if a.assigned_owner == "Alice"]
        assert len(alice_actions) > 0

    @pytest.mark.anyio
    async def test_action_with_mention(self):
        req = _req(
            ("Alice", "Action item: @dave execute the rollback and verify recovery."),
            turn=1,
        )
        r = await ENGINE.analyze(req)
        assert len(r.actions) > 0
        dave_actions = [a for a in r.actions if a.assigned_owner and "dave" in a.assigned_owner.lower()]
        assert len(dave_actions) > 0


import re  # needed for Hindi character regex in test
