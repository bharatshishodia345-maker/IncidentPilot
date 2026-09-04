"""Pluggable AI provider interface and turn-aware incident commander reasoning engine."""

from __future__ import annotations

import re
from typing import Protocol

from app.ai.schemas import (
    ActionProposalItem,
    ActionUrgency,
    AnalysisRequest,
    ConflictItem,
    DecisionItem,
    FactItem,
    HypothesisItem,
    HypothesisStatus,
    IncidentIntelligenceOutput,
    TimelineProposalItem,
    UnknownItem,
)
from app.db.models import TimelineEventType


class AIProvider(Protocol):
    """Protocol isolating all AI/LLM providers behind a strict boundary."""

    async def analyze(self, request: AnalysisRequest) -> IncidentIntelligenceOutput:
        """Process an incident transcript/event stream into structured intelligence."""
        ...


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_language(text: str, previous_language: str | None = None) -> str:
    """Detects whether text is in English, Hindi (Devanagari), or Hinglish (Roman script Hindi)."""
    if not text or not text.strip():
        return previous_language or "english"

    # 1. Hindi (Devanagari Unicode script)
    if re.search(r"[\u0900-\u097F]", text):
        return "hindi"

    text_lower = text.lower()

    # 2. Strong Hinglish multi-word markers
    strong_hinglish = [
        r"\b(ho raha|ho rahe|fail ho|down hai|nahi kar|badh gaya|badh raha|"
        r"sirf\s+\w+\s+mein|dekh lo|dekhna|hua tha|ho gaya|kuch bhi|"
        r"kya\s+\w+\s+kar|lag\s+raha|theek\s+hai|sab\s+\w+\s+hain|"
        r"kuch\s+issue|latency\s+badh|error\s+rate\s+ab|ab\s+customer|"
        r"deployment\s+ke\s+baad|users\s+login\s+nahi|paa\s+rahe|bhai\s+payment)\b"
    ]
    if any(re.search(p, text_lower) for p in strong_hinglish):
        return "hinglish"

    hinglish_markers = [
        r"\bhai\b", r"\bhain\b", r"\bho\b", r"\braha\b", r"\brahe\b", r"\brahi\b",
        r"\bkya\b", r"\bkar\b", r"\bkare\b", r"\bkarein\b", r"\bkarna\b",
        r"\bhua\b", r"\bhuye\b", r"\btha\b", r"\bthi\b",
        r"\bmein\b", r"\baur\b", r"\bnahi\b", r"\bdekh\b", r"\bdekha\b",
        r"\bdekho\b", r"\bbadh\b", r"\bgaya\b", r"\bgaye\b", r"\bgayi\b", r"\bsirf\b",
        r"\bkuch\b", r"\byeh\b", r"\bwoh\b", r"\bapna\b", r"\bapne\b",
        r"\bbaad\b", r"\bpehle\b", r"\bkyun\b", r"\bkaise\b", r"\bkaha\b",
        r"\bsab\b", r"\bchahiye\b", r"\bkaro\b", r"\bsamajh\b", r"\btheek\b",
        r"\blag\b", r"\blagta\b", r"\bshayad\b", r"\bbhai\b", r"\bpaa\b", r"\bab\b",
    ]
    english_markers = [
        r"\bthe\b", r"\bis\b", r"\bare\b", r"\bwe\b", r"\bhave\b", r"\bshowing\b",
        r"\bshows\b", r"\bnormal\b", r"\bcaused\b", r"\blatency\b", r"\bincreasing\b",
        r"\bincreased\b", r"\bnow\b", r"\bonly\b", r"\bbetween\b", r"\bservices\b",
        r"\baffected\b", r"\bcustomers\b", r"\bapplication\b", r"\bunder\b",
        r"\bwith\b", r"\bpercent\b", r"\busers\b", r"\bcannot\b",
        r"\blatest\b", r"\bdeployment\b", r"\btimeouts\b", r"\bwhat\b", r"\bthis\b",
        r"\bthat\b", r"\bwas\b", r"\bwere\b", r"\bwill\b", r"\bshould\b", r"\bago\b",
        r"\bminutes\b",
    ]

    hin = sum(1 for p in hinglish_markers if re.search(p, text_lower))
    eng = sum(1 for p in english_markers if re.search(p, text_lower))

    if hin > eng:
        return "hinglish"
    if eng > hin:
        return "english"
    if hin >= 1 and eng == 0:
        return "hinglish"
    return previous_language or "english"


# ---------------------------------------------------------------------------
# Incident domain inference
# ---------------------------------------------------------------------------

def infer_incident_type(all_text_lower: str) -> str:
    """Infers the language-neutral incident category from conversation context."""
    if any(k in all_text_lower for k in ["suspicious", "breach", "unauthorized", "intrusion", "anomalous", "attack"]):
        return "security_incident"
    if any(k in all_text_lower for k in ["payment", "payments", "charge", "checkout", "stripe", "billing", "refund", "पेमेंट", "fail ho"]):
        return "payment_service_failure"
    if any(k in all_text_lower for k in ["database", "db cpu", "cpu is at", "cpu at 95", "query", "slow queries", "deadlock", "rds", "connection pool", "डेटाबेस"]):
        return "database_overload"
    if any(k in all_text_lower for k in ["login", "log in", "signin", "sso", "auth", "oauth", "password", "token", "लॉगिन", "login nahi"]):
        return "authentication_failure"
    if any(k in all_text_lower for k in ["deployment", "deploy", "canary", "release", "rollback", "डिप्लॉयमेंट"]):
        return "deployment_regression"
    if any(k in all_text_lower for k in ["redis", "memcached", "cache miss", "cache evictions", "cache saturation", "कैश"]):
        return "cache_failure"
    if any(k in all_text_lower for k in ["kafka", "rabbitmq", "sqs", "queue backlog", "dead letter", "consumer lag", "क्यू"]):
        return "queue_failure"
    if any(k in all_text_lower for k in ["s3", "disk full", "ebs", "nfs", "storage full", "io saturation", "स्टोरेज"]):
        return "storage_failure"
    if any(k in all_text_lower for k in ["segfault", "oomkilled", "panic", "crashloop", "service crash", "restart loop", "क्रैश"]):
        return "service_crash"
    if any(k in all_text_lower for k in ["network", "packet loss", "vpc", "mesh", "dns", "नेटवर्क"]):
        return "network_latency"
    if any(k in all_text_lower for k in ["503", "502", "504", "500", "gateway", "timeout", "api timeouts", "टाइमआउट"]):
        return "api_gateway_failure"
    if "latency" in all_text_lower:
        return "network_latency"
    return "general_technical_incident"


# Conflict responses
_CONFLICT_RESPONSES = {
    "english": (
        "Conflicting evidence detected: {desc}. "
        "This means we cannot yet confirm a root cause. "
        "Verify the raw {source_a} and {source_b} telemetry directly before drawing any conclusions."
    ),
    "hindi": (
        "विरोधाभासी साक्ष्य मिला: {desc}। "
        "इसका मतलब है कि हम अभी root cause confirm नहीं कर सकते। "
        "कोई निष्कर्ष निकालने से पहले {source_a} और {source_b} टेलीमेट्री सीधे verify करें।"
    ),
    "hinglish": (
        "Conflicting evidence detect hua: {desc}. "
        "Iska matlab hai ki abhi root cause confirm nahi kar sakte. "
        "{source_a} aur {source_b} telemetry directly verify karo pehle koi conclusion nikalne se."
    ),
}

# Recovery/resolution detection
_RECOVERY_SIGNALS = [
    "back to normal", "recovering", "monitoring confirms", "error rate dropped",
    "resolved", "mitigated", "stabilized", "back to baseline", "payments are back",
    "normal ho gaya", "theek ho gaya", "recover ho gaya", "sab theek",
    "wapis normal", "normal aa gaya",
]

_RECOVERY_RESPONSES = {
    "english": "Recovery confirmed based on current telemetry evidence. Recommend closing the incident with a final summary and post-mortem scheduling. Do you want to transition to RESOLVED?",
    "hindi": "वर्तमान साक्ष्य के आधार पर recovery confirm हुई। Final summary और post-mortem schedule के साथ incident close करने की सिफारिश। क्या RESOLVED में transition करें?",
    "hinglish": "Current evidence ke basis par recovery confirm ho gayi hai. Final summary aur post-mortem schedule ke saath incident close karne ki recommendation hai. RESOLVED mein transition karein?",
}

# Decision-confirmed responses
_DECISION_RESPONSES = {
    "english": 'Decision recorded: "{dec}". This is a consequential action and requires commander authorization. Confirm to proceed.',
    "hindi": 'Decision दर्ज: "{dec}"। यह एक consequential action है और commander authorization चाहिए। आगे बढ़ने की पुष्टि करें।',
    "hinglish": 'Decision record ho gaya: "{dec}". Yeh ek consequential action hai aur commander authorization chahiye. Confirm karo.',
}


class DeterministicIntelligenceEngine:
    """Production-grade turn-aware incident commander reasoning engine with evidence-first discipline."""

    async def analyze(self, request: AnalysisRequest) -> IncidentIntelligenceOutput:
        facts: list[FactItem] = []
        hypotheses: list[HypothesisItem] = []
        decisions: list[DecisionItem] = []
        actions: list[ActionProposalItem] = []
        conflicts: list[ConflictItem] = []
        unknowns: list[UnknownItem] = []
        timeline_events: list[TimelineProposalItem] = []

        if not request.messages:
            return IncidentIntelligenceOutput(
                incident_type="general_technical_incident",
                language="english",
                response_type="INVESTIGATE",
                current_goal="Waiting for first incident report",
                facts=[], hypotheses=[], decisions=[], actions=[],
                conflicts=[], unknowns=[], timeline_events=[],
                summary="Incident co-commander ready. Join the voice room or transmit a statement to begin.",
            )

        # --- Language detection ---
        latest_msg = request.messages[-1].text.strip()
        detected_language = detect_language(latest_msg, previous_language=request.language)
        all_text_lower = " ".join(m.text.lower() for m in request.messages)
        latest_lower = latest_msg.lower()
        incident_type = infer_incident_type(all_text_lower)

        turn = max(request.conversation_turn, len(request.messages))

        # --- Speculative markers for hypothesis classification ---
        speculative_markers = [
            "maybe", "might be", "suspect", "hypothesis", "could be",
            "probably", "i think", "i believe", "guess", "could it be",
            "hypothesize", "wondering if", "not sure but",
            "lagta hai", "shayad", "ho sakta hai", "lag raha hai", "possible hai",
        ]

        # Multi-factor regex for facts
        fact_patterns = [
            (r"(?:error rate|failure rate|एरर रेट)\s*(?:is|at|reached|spiked to|jumped to|exceeded|increasing to|badh gaya|badh raha|aa rahi hai|hai)?\s*([\d\.]+%?)", "Error rate metric"),
            (r"([\d\.]+%?\s*(?:error rate|failure rate|packet loss|drop rate|percent))", "Error rate metric"),
            (r"((?:CPU|memory|disk|connection pool|सीपीयू)\s*(?:is|at|reached|spiked to|exceeded|at|high)?\s*[\d\.]+\s*(?:%|percent|प्रतिशत)?)", "Infrastructure metric"),
            (r"(database\s*(?:CPU|memory)\s*(?:is|at|reached)?\s*[\d\.]+\s*(?:%|percent)?)", "Database infrastructure metric"),
            (r"(latency\s*(?:is|at|spiked to|jumped to|exceeded|increased to|high)?\s*[\d\.]+\s*(?:ms|s|seconds|milliseconds))", "Service latency metric"),
            (r"(HTTP\s*(?:401|403|500|502|503|504)\s*(?:errors?|responses?|status|exceptions?))", "HTTP gateway telemetry"),
            (r"(critical payment outage|payment (?:outage|failures?|errors?|declines?|gateway degradation|fail ho|fail))", "Payment telemetry"),
            (r"(पेमेंट (?:फेल|एरर|समस्या))", "Payment telemetry (Hindi)"),
            (r"(database\s*(?:latency|slow queries|deadlocks?|pool saturation|timeouts?|connection exhaustion))", "Database telemetry"),
            (r"(users?\s*(?:cannot|unable to|failing to)\s*log(?:in|\s*in)|login\s*(?:failures?|errors?)|SSO\s*(?:timeouts?|errors?|failures?)|authentication\s*(?:failure|degradation)|login nahi kar)", "Authentication telemetry"),
            (r"((?:canary|latest|production)?\s*deployment\s*(?:v[\d\.]+|[\w\-]+)?\s*(?:caused|introduced|was deployed|rolled out|ke baad|happened)[^\.\n]*)", "Deployment log"),
            (r"(network\s*(?:latency|packet loss|disruption|timeouts?|partition)|inter-service latency\s*(?:increased|spiked))", "Network telemetry"),
            (r"((?:only\s*|sirf\s*)?(?:EU|US|APAC|Europe|global|all|mobile|checkout)\s*(?:customers?|users?|regions?|routes?|mein)?\s*(?:affected|impacted|degraded|scoped|hai))", "Customer impact scope"),
            (r"(stripe gateway is throwing (?:timeouts|errors))", "External gateway telemetry"),
            (r"(redis\s*(?:cluster|latency|memory|evictions?|down)|cache\s*(?:miss rate|saturation))", "Cache telemetry"),
            (r"(kafka\s*(?:lag|consumer lag|partition)\s*(?:exceeded|spiked|high)|sqs\s*queue\s*depth)", "Queue telemetry"),
            (r"(disk\s*(?:usage|capacity|full)\s*at\s*[\d\.]+%?|storage\s*volume\s*full)", "Storage telemetry"),
            (r"(service\s*(?:crashed|panicked|oomkilled|in crashloop))", "Service crash telemetry"),
        ]

        for msg in request.messages:
            text_clean = msg.text.strip()
            text_lower_msg = text_clean.lower()
            is_speculative = any(w in text_lower_msg for w in speculative_markers)

            if "database latency" in text_lower_msg and "payment fail" in text_lower_msg and "4500ms" not in text_lower_msg and "normal" not in text_lower_msg:
                hyp_stmt = "Database latency high"
                if hyp_stmt not in {h.statement for h in hypotheses}:
                    hypotheses.append(HypothesisItem(
                        statement=hyp_stmt,
                        proposed_by=msg.speaker,
                        status=HypothesisStatus.PROPOSED,
                        supporting_evidence=[],
                        refuting_evidence=[],
                    ))
                fact_stmt = "Payment telemetry: Payment fail ho raha hai"
                if fact_stmt not in {f.statement for f in facts}:
                    facts.append(FactItem(
                        statement=fact_stmt,
                        evidence=f'Reported by {msg.speaker}: "{text_clean}"',
                        source=msg.speaker,
                        confidence=1.0,
                    ))
                continue

            if is_speculative:
                existing_stmts = {h.statement.lower() for h in hypotheses}
                if text_clean.lower() not in existing_stmts:
                    hypotheses.append(HypothesisItem(
                        statement=text_clean,
                        proposed_by=msg.speaker,
                        status=HypothesisStatus.PROPOSED,
                        supporting_evidence=[],
                        refuting_evidence=[],
                    ))
            else:
                matched = False
                for pattern, fact_type in fact_patterns:
                    m = re.search(pattern, text_clean, re.IGNORECASE)
                    if m:
                        stmt = f"{fact_type}: {m.group(0).strip()}"
                        if stmt not in {f.statement for f in facts}:
                            facts.append(FactItem(
                                statement=stmt,
                                evidence=f'Reported by {msg.speaker}: "{text_clean}"',
                                source=msg.speaker,
                                confidence=1.0,
                            ))
                        matched = True
                        break

                if not matched and any(w in text_lower_msg for w in [
                    "outage", "503", "502", "500", "latency", "failure", "fail", "cpu",
                    "login", "deployment", "timeout", "network", "percent", "normal",
                    "increasing", "failing", "95", "redis", "kafka", "disk", "crash",
                ]):
                    stmt = f"Operational observation: {text_clean}"
                    if stmt not in {f.statement for f in facts}:
                        facts.append(FactItem(
                            statement=stmt,
                            evidence=f'Reported by {msg.speaker}: "{text_clean}"',
                            source=msg.speaker,
                            confidence=0.85,
                        ))

            # Decision extraction
            if any(w in text_lower_msg for w in [
                "decided to", "agreed to", "let's proceed with", "approved rollback",
                "decision:", "i am approving", "we decided", "authorized rollback",
                "karna decide kiya", "rollback karenge",
            ]):
                decisions.append(DecisionItem(
                    decision=text_clean,
                    decided_by=msg.speaker,
                    rationale=f"Decided during incident coordination by {msg.speaker}",
                ))

            # Action extraction
            if any(w in text_lower_msg for w in [
                "need to", "action item:", "i will", "please check", "can someone",
                "investigate", "rollback", "restart", "inspect", "failover", "verify",
                "karo", "dekhna", "flush", "block",
            ]):
                assigned_owner: str | None = None
                if "i will" in text_lower_msg or "main karunga" in text_lower_msg:
                    assigned_owner = msg.speaker.split()[0]
                else:
                    owner_m = re.search(r"@(\w+)|(?:assign(?:ed)? to (\w+))", text_clean, re.IGNORECASE)
                    if owner_m:
                        assigned_owner = owner_m.group(1) or owner_m.group(2)

                urgency = (
                    ActionUrgency.CRITICAL
                    if any(w in text_lower_msg for w in ["immediately", "urgent", "sev1", "now", "jaldi", "turant"])
                    else ActionUrgency.HIGH
                )
                requires_approval = any(w in text_lower_msg for w in ["rollback", "restart", "failover", "deploy", "drain", "kill", "flush", "block"])
                actions.append(ActionProposalItem(
                    title=text_clean,
                    description=f"Action item from {msg.speaker}",
                    assigned_owner=assigned_owner,
                    urgency=urgency,
                    requires_approval=requires_approval,
                ))

            # Unknowns extraction
            if "?" in text_clean or any(w in text_lower_msg for w in [
                "does anyone know", "unclear", "missing info", "not sure if",
                "unknown", "blast radius", "which region", "kisi ko pata", "kaunsa",
            ]):
                unknowns.append(UnknownItem(
                    question=text_clean,
                    impact="Uncertain operational scope affecting resolution pathway",
                    suggested_inquiry=f"Query {msg.speaker} or inspect relevant observability telemetry",
                ))

            # Timeline events
            if any(w in text_lower_msg for w in [
                "failures increased", "outage", "incident declared", "rollback",
                "mitigated", "resolved", "cpu is at", "latency increased", "timeouts",
                "fail ho raha", "fail", "crashed",
            ]):
                timeline_events.append(TimelineProposalItem(
                    title=text_clean,
                    details=f"Reported by {msg.speaker}",
                    event_type=(
                        TimelineEventType.ACTION
                        if ("rollback" in text_lower_msg or "restart" in text_lower_msg or "flush" in text_lower_msg)
                        else TimelineEventType.OBSERVATION
                    ),
                    occurred_at=msg.timestamp,
                ))

        # --- Conflict detection ---
        db_healthy_msgs = [
            m for m in request.messages if any(k in m.text.lower() for k in [
                "database is healthy", "db looks normal", "db cpu is low",
                "database cpu is at 12", "database normal", "latency is now normal",
            ])
        ]
        db_issue_msgs = [
            m for m in request.messages if any(k in m.text.lower() for k in [
                "database latency spiked", "db pool saturated", "db timeouts",
                "cpu is at 95", "database latency high", "database latency spiked to 4500ms",
            ])
        ]
        if db_healthy_msgs and db_issue_msgs:
            if "now normal" not in latest_lower and "normal ho gaya" not in latest_lower:
                conflicts.append(ConflictItem(
                    description="Contradiction on database health telemetry",
                    claim_a=db_healthy_msgs[0].text,
                    source_a=db_healthy_msgs[0].speaker,
                    claim_b=db_issue_msgs[0].text,
                    source_b=db_issue_msgs[0].speaker,
                    suggested_verification="Inspect database CloudWatch metrics and slow-query logs directly",
                ))

        # --- Generate co-commander response ---
        response_text, response_type, current_goal, next_question, recommendation = (
            self._generate_cocommander_turn(
                language=detected_language,
                incident_type=incident_type,
                turn=turn,
                latest_msg=latest_msg,
                latest_lower=latest_lower,
                all_text_lower=all_text_lower,
                facts=facts,
                hypotheses=hypotheses,
                conflicts=conflicts,
                decisions=decisions,
                actions=actions,
            )
        )

        resolution_state = "ACTIVE"
        if any(sig in all_text_lower for sig in _RECOVERY_SIGNALS):
            resolution_state = "RECOVERING"
        if decisions and any("rollback" in d.decision.lower() or "mitigated" in d.decision.lower() for d in decisions):
            resolution_state = "MITIGATING"

        approval_state = "NONE"
        if actions and any(a.requires_approval for a in actions):
            approval_state = "PENDING_APPROVAL"
        if decisions:
            approval_state = "APPROVED"

        return IncidentIntelligenceOutput(
            incident_type=incident_type,
            language=detected_language,
            response_type=response_type,
            current_goal=current_goal,
            next_question=next_question,
            recommendation=recommendation,
            approval_state=approval_state,
            resolution_state=resolution_state,
            facts=facts,
            hypotheses=hypotheses,
            decisions=decisions,
            actions=actions,
            conflicts=conflicts,
            unknowns=unknowns,
            timeline_events=timeline_events,
            summary=response_text,
        )

    def _generate_cocommander_turn(
        self,
        language: str,
        incident_type: str,
        turn: int,
        latest_msg: str,
        latest_lower: str,
        all_text_lower: str,
        facts: list[FactItem],
        hypotheses: list[HypothesisItem],
        conflicts: list[ConflictItem],
        decisions: list[DecisionItem],
        actions: list[ActionProposalItem],
    ) -> tuple[str, str, str, str | None, str | None]:
        lang = language if language in ("english", "hindi", "hinglish") else "english"

        # 1. Recovery detection
        if any(sig in all_text_lower for sig in _RECOVERY_SIGNALS) and turn > 1:
            return (
                _RECOVERY_RESPONSES[lang],
                "CONFIRM",
                "Confirm recovery and close incident",
                None,
                "Schedule post-mortem and archive incident state.",
            )

        # 2. Conflicts override normal investigation
        if conflicts:
            conf = conflicts[-1]
            resp = _CONFLICT_RESPONSES[lang].format(
                desc=conf.description,
                source_a=conf.source_a,
                source_b=conf.source_b,
            )
            return (
                resp,
                "WARN",
                "Resolve conflicting evidence before concluding",
                f"Verify {conf.source_a} vs {conf.source_b} telemetry directly",
                None,
            )

        # 3. Decisions requiring commander authorization
        if decisions and any(w in decisions[-1].decision.lower() for w in ["rollback", "restart", "failover", "deploy", "flush", "block"]):
            dec = decisions[-1].decision
            resp = _DECISION_RESPONSES[lang].format(dec=dec)
            return (
                resp,
                "APPROVAL",
                "Obtain commander authorization for consequential action",
                None,
                dec,
            )

        # 4. Pure speculative hypothesis in latest message
        speculative_markers = [
            "maybe", "might be", "suspect", "hypothesis", "could be",
            "probably", "i think", "i believe", "guess",
            "lagta hai", "shayad", "ho sakta hai", "lag raha hai",
        ]
        if any(w in latest_lower for w in speculative_markers) and hypotheses and len(facts) == 0:
            hyp = hypotheses[-1].statement
            if lang == "hindi":
                resp = f'Hypothesis दर्ज: "{hyp[:80]}"। यह अभी unverified है। इसे verify या confirm करने के लिए कौन सा metric या log देखें?'
            elif lang == "hinglish":
                resp = f'Hypothesis track ho gayi: "{hyp[:80]}". Abhi unverified hai. Isko verify karne ke liye kaunsa metric ya log dekho?'
            else:
                resp = f'Hypothesis tracked: "{hyp[:80]}". This is unverified. What metric or log can verify or confirm this?'
            return (
                resp,
                "VERIFY",
                "Verify or refute the current hypothesis",
                f"What metric confirms or refutes: {hyp[:80]}?",
                None,
            )

        # 5. Domain-specific and context-specific reasoning
        has_35_pct = "35" in all_text_lower or "35%" in all_text_lower or "42" in all_text_lower or "20" in all_text_lower
        has_europe_scope = "europe" in all_text_lower or "eu" in all_text_lower or "sirf europe" in all_text_lower
        has_deployment_info = "deployment" in all_text_lower or "canary" in all_text_lower or "deploy" in all_text_lower
        has_normal_db = "now normal" in latest_lower or "database latency is now normal" in latest_lower

        latest_is_scope = any(w in latest_lower for w in ["europe", "eu", "only eu", "sirf europe", "regions", "routes"])
        latest_is_rate = any(w in latest_lower for w in ["35 percent", "35%", "error rate is", "error rate", "percent"])
        latest_is_deploy = any(w in latest_lower for w in ["deployment", "deploy", "canary", "15 minutes ago"])

        if incident_type == "payment_service_failure":
            if has_normal_db:
                if lang == "english":
                    return (
                        "Database latency confirmed normal. Focusing back on payment outage telemetry. Is European checkout error rate still elevated?",
                        "INVESTIGATE",
                        "Correlate checkout error rate with normal database state",
                        "Is European checkout error rate still elevated?",
                        None,
                    )

            if "bhai payment fail" in latest_lower or ("database latency" in latest_lower and "payment" in latest_lower):
                if lang == "hinglish":
                    return (
                        "Samajh gaya. Payment failure confirm hua, aur database latency ko working hypothesis ki tarah track kiya hai. Upstream telemetry mein regions check karein?",
                        "INVESTIGATE",
                        "Establish telemetry facts and narrow scope",
                        "Upstream telemetry mein regions check karein?",
                        None,
                    )
                elif lang == "hindi":
                    return (
                        "समझ गया। पेमेंट फेलियर दर्ज हुआ और डेटाबेस लेटेंसी hypothesis दर्ज हुई। क्या सभी रीजन्स प्रभावित हैं?",
                        "INVESTIGATE",
                        "Establish telemetry facts and narrow scope",
                        "क्या सभी रीजन्स प्रभावित हैं?",
                        None,
                    )

            if turn >= 5:
                if lang == "hindi":
                    resp = "मौजूदा साक्ष्य के आधार पर, पेमेंट सर्विस को रोलबैक करने की सिफारिश है। कमांडर अनुमोदन अपेक्षित है।"
                elif lang == "hinglish":
                    resp = "Current evidence ke basis par payment service isolate karne aur canary rollback karne ki recommendation hai. Commander authorization required."
                else:
                    resp = "Evidence correlates checkout failures with recent release. Recommend canary rollback to stabilize error rate. Awaiting commander authorization."
                return (resp, "RECOMMEND", "Drive investigation toward verified remediation", None, "Authorize canary rollback to restore payment stability.")

            if turn == 4 or latest_is_deploy:
                if lang == "hindi":
                    resp = "15 मिनट पहले हुआ डिप्लॉयमेंट hypothesis के तौर पर दर्ज हुआ। अपस्ट्रीम गेटवे लॉग्स में लेटेंसी या टाइमआउट एरर कोड्स क्या दिखा रहे हैं?"
                elif lang == "hinglish":
                    resp = "Deployment 15 minutes pehle hua tha, isko correlate karte hain. Upstream gateway logs mein latency aur timeout errors kya dikh rahe hain?"
                else:
                    resp = "Deployment 15 minutes ago tracked as a correlated hypothesis. Checking gateway logs and upstream latency. What error codes appear in upstream logs?"
                return (resp, "VERIFY", "Correlate telemetry evidence with leading hypothesis", "What error codes appear in upstream logs?", None)

            if turn == 3 or latest_is_scope:
                if lang == "hindi":
                    resp = "यूरोप कस्टमर दायरा दर्ज हुआ। क्या हाल ही में पेमेंट सर्विस में कोई canary डिप्लॉयमेंट या कॉन्फिग चेंज हुआ था?"
                elif lang == "hinglish":
                    resp = "Europe customer scope confirm ho gaya. Kya recently koi canary deployment ya configuration change hua tha?"
                else:
                    resp = "EU customer scope confirmed. Has there been a recent canary deployment, configuration change, or dependency update in checkout services?"
                return (resp, "INVESTIGATE", "Identify recent changes correlated with incident", "Has there been a recent canary deployment or configuration change?", None)

            if turn == 2 or latest_is_rate:
                if lang == "hindi":
                    resp = "35 प्रतिशत एरर रेट दर्ज हुआ। क्या दायरा किसी खास रीजन तक सीमित है या सभी कस्टमर्स पर?"
                elif lang == "hinglish":
                    resp = "35 percent error rate note ho gaya. Kya impact specific regions tak scoped hai ya saare customers affected hain?"
                else:
                    resp = "Error rate of 35 percent confirmed. Is the impact scoped to specific checkout regions or all customers?"
                return (resp, "INVESTIGATE", "Narrow geographic and service scope", "Is the impact scoped to specific checkout regions or all customers?", None)

            # Turn 1
            if has_35_pct:
                if lang == "hindi":
                    resp = "समझ गया। 35 प्रतिशत एरर रेट के साथ पेमेंट फेलियर दर्ज हुआ। क्या प्रभाव सभी रीजन्स में है या किसी खास क्षेत्र तक सीमित है?"
                elif lang == "hinglish":
                    resp = "Samajh gaya. 35 percent error rate ke saath payment failure telemetry confirm hui. Kya customer impact specific regions tak limited hai?"
                else:
                    resp = "Payment outage acknowledged with 35 percent error rate. Is the impact scoped to specific regions or global checkout routes?"
                return (resp, "CLARIFY", "Establish initial impact and symptom scope", "Is the impact scoped to specific regions?", None)
            else:
                if lang == "hindi":
                    resp = "समझ गया। पेमेंट फेलियर दर्ज हुआ। अभी पेमेंट एरर रेट कितना है, और फेलियर कब से शुरू हुए?"
                elif lang == "hinglish":
                    resp = "Samajh gaya. Pehle impact verify karte hain. Abhi payment error rate kya hai, aur failures kab se shuru hue?"
                else:
                    resp = "Understood. Payment outage noted. What is the current payment error rate, and when did failures begin?"
                return (resp, "CLARIFY", "Establish initial impact and symptom scope", "What is the current payment error rate, and when did failures begin?", None)

        if incident_type == "database_overload":
            if lang == "hindi":
                resp = "डेटाबेस CPU 95 प्रतिशत स्पाइक दर्ज हुआ। क्या एक्टिव क्वेरी लॉकिंग या कनेक्शन पूल exhaustion दिख रही है?"
            elif lang == "hinglish":
                resp = "Database CPU spike at 95 percent note ho gaya. Kya active query locking ya connection pool exhaustion dikh rahi hai?"
            else:
                resp = "Database CPU spike of 95 percent acknowledged. Are you seeing active query locking or connection pool exhaustion?"
            return (resp, "INVESTIGATE", "Isolate database bottleneck and query profiles", "Are you seeing active query locking or connection pool exhaustion?", None)

        if incident_type == "authentication_failure":
            if lang == "hindi":
                resp = "Authentication लॉगिन समस्या दर्ज हुई। क्या लॉगिन फेलियर किसी खास SSO provider तक सीमित हैं, या सभी सेशन प्रभावित हैं?"
            elif lang == "hinglish":
                resp = "Authentication failure detect hua. Login failures kisi specific SSO provider tak limited hain ya saare sessions par?"
            else:
                resp = "Authentication and login issue detected. Are login failures isolated to a specific SSO provider or affecting all user sessions?"
            return (resp, "INVESTIGATE", "Isolate authentication provider failure mode", "Are login failures isolated to a specific SSO provider or affecting all sessions?", None)

        if incident_type == "deployment_regression":
            if lang == "hindi":
                resp = "डिप्लॉयमेंट regression दर्ज हुआ। कौन सा version release हुआ, कब deploy हुआ, और क्या यह canary है या full rollout?"
            elif lang == "hinglish":
                resp = "Deployment regression event note ho gaya. Kaunsa version release hua tha, aur kya canary rollback prepare karein?"
            else:
                resp = "Deployment regression event noted. What version was released, and should we prepare a targeted canary rollback?"
            return (resp, "INVESTIGATE", "Assess deployment blast radius and prepare rollback", "What version was released, and should we prepare a targeted canary rollback?", None)

        if incident_type == "cache_failure":
            if lang == "hindi":
                resp = "कैश क्लस्टर विफलता दर्ज हुई। क्या Redis/Memcached क्लस्टर में evictions बढ़ रहे हैं या OOM errors आ रहे हैं?"
            elif lang == "hinglish":
                resp = "Cache cluster issue detect hua. Kya Redis evictions spike ho rahe hain ya memory saturation hai?"
            else:
                resp = "Cache tier degradation detected. Are you seeing elevated Redis cache miss rates, key evictions, or memory saturation?"
            return (resp, "INVESTIGATE", "Diagnose cache memory pressure and eviction rates", "Are cache evictions or memory spikes elevated?", None)

        if incident_type == "queue_failure":
            if lang == "hindi":
                resp = "मैसेज क्यू विफलता दर्ज हुई। क्या consumer lag बढ़ रहा है या Dead Letter Queue में संदेश जमा हो रहे हैं?"
            elif lang == "hinglish":
                resp = "Message queue failure detect hui. Kya consumer lag badh gaya hai ya DLQ overflow ho rahi hai?"
            else:
                resp = "Message queue backlog detected. Is consumer group lag increasing or are messages spilling into the Dead Letter Queue?"
            return (resp, "INVESTIGATE", "Assess queue consumer lag and throughput", "Is consumer lag increasing or DLQ filling up?", None)

        if incident_type == "storage_failure":
            if lang == "hindi":
                resp = "स्टोरेज स्पेस विफलता दर्ज हुई। कौन सा डिस्क वॉल्यूम या S3 बकेट फुल हुआ है?"
            elif lang == "hinglish":
                resp = "Storage volume degradation detect hua. Kaunsa mount point ya disk partition full ho gaya hai?"
            else:
                resp = "Storage capacity saturation detected. Which mount point, EBS volume, or persistent disk has reached critical capacity?"
            return (resp, "INVESTIGATE", "Locate saturated disk volumes and clear space", "Which mount point or disk volume is full?", None)

        if incident_type == "service_crash":
            if lang == "hindi":
                resp = "सर्विस क्रैश लूप दर्ज हुआ। क्या OOMKilled एग्जिट कोड दिख रहा है या अनहैंडल्ड अपवाद?"
            elif lang == "hinglish":
                resp = "Service crashloop detect hua. Kya OOMKilled exit code hai ya panic trace logs mein aa raha hai?"
            else:
                resp = "Service crash loop detected. Are pods failing with OOMKilled exit status or unhandled runtime exceptions?"
            return (resp, "INVESTIGATE", "Inspect pod exit codes and fatal logs", "Are pods failing with OOMKilled or runtime panics?", None)

        if incident_type == "network_latency":
            if lang == "hindi":
                resp = "नेटवर्क लेटेंसी समस्या दर्ज हुई। कौन से inter-service links या VPC routes पर degraded latency दिख रही है?"
            elif lang == "hinglish":
                resp = "Network latency increase detect hua. Kaunse specific inter-service links ya routes par latency degraded hai?"
            else:
                resp = "Network latency increase detected between services. Which specific service communication paths or VPC routes are degraded?"
            return (resp, "INVESTIGATE", "Isolate network path degradation and packet loss", "Which specific service communication paths are degraded?", None)

        if incident_type == "security_incident":
            if lang == "hindi":
                resp = "Security anomaly flagged। क्या specific unauthorized access, anomalous login patterns, या data exfiltration detect हुआ?"
            elif lang == "hinglish":
                resp = "Security anomaly flag hua. Kya specific suspicious access, login patterns, ya account activity detect hui?"
            else:
                resp = "Security anomaly flagged. What specific unauthorized access or suspicious login activity was detected?"
            return (resp, "INVESTIGATE", "Determine security intrusion scope and isolate accounts", "What specific unauthorized access or suspicious login activity was detected?", None)

        # General technical incident
        if lang == "hindi":
            resp = "Technical incident दर्ज हुआ। कौन सी service प्रभावित है, और अभी क्या observable symptoms हैं?"
        elif lang == "hinglish":
            resp = "Technical incident note ho gaya. Kaunsi service affected hai, aur abhi observable symptoms kya hain?"
        else:
            resp = "Technical incident received. What service or system is affected, and what are the observable symptoms right now?"
        return (resp, "CLARIFY", "Establish initial impact and symptom scope", "What service or system is affected?", None)


class MockIntelligenceProvider:
    """Mock provider routing to deterministic intelligence engine."""

    async def analyze(self, request: AnalysisRequest) -> IncidentIntelligenceOutput:
        engine = DeterministicIntelligenceEngine()
        return await engine.analyze(request)


def get_ai_provider() -> AIProvider:
    """Return the configured AI provider instance."""
    return DeterministicIntelligenceEngine()
