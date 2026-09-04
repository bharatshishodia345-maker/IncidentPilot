"""Test verification for dynamic multi-domain incident reasoning."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from app.ai.provider import DeterministicIntelligenceEngine
from app.ai.schemas import AnalysisRequest, TranscriptMessage, IntelligenceSourceType


@pytest.mark.anyio
async def test_five_diverse_incident_responses():
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    # Test A: Payment Outage
    res_a = await engine.analyze(
        AnalysisRequest(
            messages=[
                TranscriptMessage(
                    speaker="Alice (Commander)",
                    text="We have a payment outage.",
                    source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
                    timestamp=now,
                )
            ]
        )
    )
    assert "payment" in res_a.summary.lower()
    assert len(res_a.facts) >= 1

    # Test B: Database CPU at 95 percent
    res_b = await engine.analyze(
        AnalysisRequest(
            messages=[
                TranscriptMessage(
                    speaker="Bob (DB Lead)",
                    text="The database CPU is at 95 percent.",
                    source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
                    timestamp=now,
                )
            ]
        )
    )
    assert "database cpu" in res_b.summary.lower() or "95" in res_b.summary
    assert res_b.summary != res_a.summary

    # Test C: Users cannot log into the application
    res_c = await engine.analyze(
        AnalysisRequest(
            messages=[
                TranscriptMessage(
                    speaker="Charlie (Auth)",
                    text="Users cannot log into the application.",
                    source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
                    timestamp=now,
                )
            ]
        )
    )
    assert "authentication" in res_c.summary.lower() or "login" in res_c.summary.lower()
    assert res_c.summary != res_a.summary
    assert res_c.summary != res_b.summary

    # Test D: The latest deployment caused API timeouts
    res_d = await engine.analyze(
        AnalysisRequest(
            messages=[
                TranscriptMessage(
                    speaker="Dave (Release Lead)",
                    text="The latest deployment caused API timeouts.",
                    source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
                    timestamp=now,
                )
            ]
        )
    )
    assert "deployment" in res_d.summary.lower() or "rollback" in res_d.summary.lower()
    assert res_d.summary != res_a.summary
    assert res_d.summary != res_c.summary

    # Test E: Network latency increased between services
    res_e = await engine.analyze(
        AnalysisRequest(
            messages=[
                TranscriptMessage(
                    speaker="Eve (Infra)",
                    text="Network latency increased between services.",
                    source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
                    timestamp=now,
                )
            ]
        )
    )
    assert "network" in res_e.summary.lower() or "latency" in res_e.summary.lower()
    assert res_e.summary != res_a.summary
    assert res_e.summary != res_d.summary


@pytest.mark.anyio
async def test_multi_turn_cocommander_conversation_loop():
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    # Turn 1: User reports payment failure
    msgs = [
        TranscriptMessage(speaker="Alice", text="Payments are failing.", timestamp=now)
    ]
    t1 = await engine.analyze(AnalysisRequest(messages=msgs))
    assert "payment" in t1.summary.lower()
    assert "?" in t1.summary

    # Turn 2: User provides telemetry metric
    msgs.append(TranscriptMessage(speaker="Alice", text="Yes, error rate is 35 percent.", timestamp=now))
    t2 = await engine.analyze(AnalysisRequest(messages=msgs))
    assert "35 percent" in t2.summary.lower() or "35%" in t2.summary.lower() or "error rate" in t2.summary.lower()
    assert "regions" in t2.summary.lower() or "scope" in t2.summary.lower() or "customers" in t2.summary.lower()

    # Turn 3: User scopes to EU
    msgs.append(TranscriptMessage(speaker="Alice", text="Only EU customers.", timestamp=now))
    t3 = await engine.analyze(AnalysisRequest(messages=msgs))
    assert "eu" in t3.summary.lower()
    assert "deployment" in t3.summary.lower() or "configuration" in t3.summary.lower()
