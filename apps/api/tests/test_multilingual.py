"""Comprehensive test suite for English, Hindi, and Hinglish Incident Intelligence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from app.ai.provider import DeterministicIntelligenceEngine, detect_language, infer_incident_type
from app.ai.schemas import AnalysisRequest, TranscriptMessage, IntelligenceSourceType


def test_language_detection_unit():
    # English sentences
    assert detect_language("Payment failures are increasing.") == "english"
    assert detect_language("The database CPU is at 95 percent.") == "english"
    assert detect_language("The latest deployment was 15 minutes ago.") == "english"
    assert detect_language("The database latency is now normal.") == "english"

    # Hinglish sentences (Roman script Hindi)
    assert detect_language("Payment fail ho raha hai.") == "hinglish"
    assert detect_language("Bhai payment fail ho raha hai aur database latency bhi high hai.") == "hinglish"
    assert detect_language("Error rate ab 20 percent hai.") == "hinglish"
    assert detect_language("Ab customer impact sirf Europe mein hai.") == "hinglish"
    assert detect_language("Deployment ke baad issue start hua.") == "hinglish"
    assert detect_language("Users login nahi kar paa rahe.") == "hinglish"

    # Hindi sentences (Devanagari script)
    assert detect_language("पेमेंट फेल हो रहे हैं और एरर बढ़ रहा है।") == "hindi"
    assert detect_language("डेटाबेस में समस्या आ रही है।") == "hindi"


@pytest.mark.anyio
async def test_1_english_incident_understanding():
    """TEST 1 — ENGLISH:
    User: 'Payment failures are increasing. Monitoring shows a 35 percent error rate.'
    Expected: English response, correct fact extraction.
    """
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    msg = TranscriptMessage(
        speaker="Alice (Commander)",
        text="Payment failures are increasing. Monitoring shows a 35 percent error rate.",
        timestamp=now,
    )

    result = await engine.analyze(AnalysisRequest(messages=[msg]))

    assert result.language == "english"
    assert result.incident_type == "payment_service_failure"
    assert len(result.facts) >= 1
    # Check that response is in English and context-aware
    assert any(w in result.summary.lower() for w in ["payment", "error rate", "35%", "35 percent", "telemetry", "regions"])
    # Not using generic placeholder
    assert "please provide more information" not in result.summary.lower()


@pytest.mark.anyio
async def test_2_hindi_incident_understanding():
    """TEST 2 — HINDI:
    User: 'Payment fail ho rahe hain aur monitoring mein error rate badh gaya hai.'
    Expected: Hindi/Hinglish natural response, correct fact extraction.
    """
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    msg = TranscriptMessage(
        speaker="Rohan (Responder)",
        text="Payment fail ho rahe hain aur monitoring mein error rate badh gaya hai.",
        timestamp=now,
    )

    result = await engine.analyze(AnalysisRequest(messages=[msg]))

    assert result.language in ["hindi", "hinglish"]
    assert result.incident_type == "payment_service_failure"
    assert len(result.facts) >= 1
    # Response must be in natural Hinglish/Hindi
    assert any(w in result.summary.lower() for w in ["samajh gaya", "payment failure", "telemetry", "confirm", "monitoring", "regions"])


@pytest.mark.anyio
async def test_3_hinglish_fact_and_hypothesis_separation():
    """TEST 3 — HINGLISH:
    User: 'Bhai payment fail ho raha hai aur database latency bhi high hai.'
    Expected: Natural Hinglish response, Payment failure = fact, Database latency = hypothesis unless verified.
    """
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    msg = TranscriptMessage(
        speaker="Amit (Backend)",
        text="Bhai payment fail ho raha hai aur database latency bhi high hai.",
        timestamp=now,
    )

    result = await engine.analyze(AnalysisRequest(messages=[msg]))

    assert result.language == "hinglish"
    assert result.incident_type == "payment_service_failure"
    
    # Verify fact and hypothesis separation
    assert len(result.facts) >= 1
    # Response should acknowledge payment failure as confirmed and database latency as hypothesis
    assert "samajh gaya" in result.summary.lower()
    assert "payment failure" in result.summary.lower() or "payment" in result.summary.lower()
    assert "database latency" in result.summary.lower() or "deployment" in result.summary.lower()


@pytest.mark.anyio
async def test_4_multilingual_language_switch_flow():
    """TEST 4 — LANGUAGE SWITCH TEST:
    Turn 1 (Hinglish): 'Payment fail ho raha hai.' -> Hinglish response
    Turn 2 (English switch): 'The database latency is now normal.' -> English response
    Turn 3 (Hinglish switch): 'Ab customer impact sirf Europe mein hai.' -> Hinglish response
    """
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    # Turn 1
    msgs = [
        TranscriptMessage(speaker="Alice", text="Payment fail ho raha hai.", timestamp=now)
    ]
    t1 = await engine.analyze(AnalysisRequest(messages=msgs))
    assert t1.language == "hinglish"
    assert "samajh gaya" in t1.summary.lower() or "payment" in t1.summary.lower()

    # Turn 2: User switches to English
    msgs.append(TranscriptMessage(speaker="Alice", text="The database latency is now normal.", timestamp=now))
    t2 = await engine.analyze(AnalysisRequest(messages=msgs, language=t1.language))
    assert t2.language == "english"
    assert "database latency" in t2.summary.lower() or "normal" in t2.summary.lower()

    # Turn 3: User switches to Hinglish
    msgs.append(TranscriptMessage(speaker="Alice", text="Ab customer impact sirf Europe mein hai.", timestamp=now))
    t3 = await engine.analyze(AnalysisRequest(messages=msgs, language=t2.language))
    assert t3.language in ["hinglish", "hindi"]
    assert "europe" in t3.summary.lower()
    assert "canary" in t3.summary.lower() or "deployment" in t3.summary.lower() or "scoped" in t3.summary.lower()


@pytest.mark.anyio
async def test_5_devanagari_hindi_script_understanding():
    """TEST 5 — DEVANAGARI SCRIPT HINDI:
    User: 'पेमेंट फेल हो रहे हैं और एरर बढ़ रहा है।'
    Expected: Hindi language detection and Devanagari Hindi response.
    """
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    msg = TranscriptMessage(
        speaker="Vikram",
        text="पेमेंट फेल हो रहे हैं और एरर बढ़ रहा है।",
        timestamp=now,
    )

    result = await engine.analyze(AnalysisRequest(messages=[msg]))
    assert result.language == "hindi"
    assert result.incident_type == "payment_service_failure"
    assert len(result.facts) >= 1
    # Check that Hindi response contains Hindi characters
    assert any(c in result.summary for c in ["समझ", "पेमेंट", "फेलियर", "मॉनिटरिंग", "एरर"])


@pytest.mark.anyio
async def test_6_diverse_incidents_in_hinglish():
    """TEST 6 — DIVERSE INCIDENTS IN HINGLISH:
    Validates Database, Login, and Deployment incidents in Hinglish.
    """
    engine = DeterministicIntelligenceEngine()
    now = datetime.now(timezone.utc)

    # 1. Database CPU high
    res_db = await engine.analyze(
        AnalysisRequest(
            messages=[
                TranscriptMessage(
                    speaker="Bob",
                    text="Database ka CPU high hai aur connection pool saturated hai.",
                    timestamp=now,
                )
            ]
        )
    )
    assert res_db.language == "hinglish"
    assert res_db.incident_type == "database_overload"
    assert "database" in res_db.summary.lower() or "connection pool" in res_db.summary.lower()

    # 2. Login failures
    res_auth = await engine.analyze(
        AnalysisRequest(
            messages=[
                TranscriptMessage(
                    speaker="Charlie",
                    text="Users login nahi kar paa rahe hain.",
                    timestamp=now,
                )
            ]
        )
    )
    assert res_auth.language == "hinglish"
    assert res_auth.incident_type == "authentication_failure"
    assert "authentication" in res_auth.summary.lower() or "login" in res_auth.summary.lower()

    # 3. Deployment issue
    res_dep = await engine.analyze(
        AnalysisRequest(
            messages=[
                TranscriptMessage(
                    speaker="Dave",
                    text="Deployment ke baad issue start hua tha.",
                    timestamp=now,
                )
            ]
        )
    )
    assert res_dep.language == "hinglish"
    assert res_dep.incident_type == "deployment_regression"
    assert "deployment" in res_dep.summary.lower() or "rollback" in res_dep.summary.lower()
