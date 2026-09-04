"""Incident Intelligence REST endpoints for conversation processing and structured artifact extraction."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import (
    AnalysisRequest,
    IncidentIntelligenceOutput,
    IntelligenceSourceType,
    TranscriptMessage,
)
from app.auth.dependencies import Principal, get_current_principal, require_roles
from app.core.exceptions import EntityNotFoundError
from app.db.models import User, UserRole
from app.db.session import get_db
from app.services.intelligence_service import IntelligenceService

router = APIRouter(tags=["intelligence"])


def _resolve_user_id(session: Session, principal: Principal) -> UUID:
    """Resolve the persistent User UUID from the authenticated principal."""
    if principal.user_id is not None:
        user = session.scalar(
            select(User).where(User.id == principal.user_id, User.organization_id == principal.organization_id)
        )
        if user is not None:
            return user.id

    user = session.scalar(
        select(User).where(User.subject == principal.subject, User.organization_id == principal.organization_id)
    )
    if user is None:
        raise EntityNotFoundError("User", f"subject={principal.subject}")
    return user.id


@router.post(
    "/incidents/{incident_id}/intelligence/analyze",
    response_model=IncidentIntelligenceOutput,
    status_code=status.HTTP_200_OK,
)
async def analyze_incident_intelligence(
    incident_id: UUID,
    payload: AnalysisRequest,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> IncidentIntelligenceOutput:
    """Process an incident transcript or telemetry stream into structured facts, hypotheses, decisions, actions, conflicts, and unknowns."""
    actor_user_id = _resolve_user_id(session, principal)

    service = IntelligenceService()
    output = await service.analyze_incident_stream(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        request=payload,
        actor_user_id=actor_user_id,
    )
    return output


@router.get(
    "/incidents/{incident_id}/intelligence/payment-demo",
    response_model=IncidentIntelligenceOutput,
    status_code=status.HTTP_200_OK,
)
async def get_payment_demo_intelligence(
    incident_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> IncidentIntelligenceOutput:
    """Execute a realistic payment outage scenario analysis demonstrating all IncidentPilot capabilities."""
    actor_user_id = _resolve_user_id(session, principal)
    now = datetime.now(timezone.utc)

    # Standard high-stakes payment outage demo dialogue
    sample_messages = [
        TranscriptMessage(
            speaker="Monitoring Bot",
            text="Payment failures increased: error rate reached 42.8% on /v1/charges with HTTP 503 responses.",
            source_type=IntelligenceSourceType.TELEMETRY_LOG,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Alice (Commander)",
            text="I am declaring SEV1. Payment failures jumped across European checkouts. We need to stabilize immediately.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Bob (Database Lead)",
            text="I suspect database latency spiked to 4500ms and DB pool saturated because of the new index migration.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Charlie (Infrastructure)",
            text="Wait, database is healthy and database CPU is at 12%, but external stripe gateway is throwing timeouts.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Alice (Commander)",
            text="Does anyone know if canary deployment v2.14 was deployed at 21:45 today?",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Dave (Release Lead)",
            text="Yes, canary deployment v2.14 was deployed at 21:45. I will inspect the checkout service diff right now.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
        TranscriptMessage(
            speaker="Alice (Commander)",
            text="We decided to rollback canary deployment v2.14 immediately. Action item: @dave execute rollback and verify.",
            source_type=IntelligenceSourceType.VOICE_TRANSCRIPT,
            timestamp=now,
        ),
    ]

    service = IntelligenceService()
    output = await service.analyze_incident_stream(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        request=AnalysisRequest(
            messages=sample_messages,
            incident_title="Payment Gateway 503 Authorization Outage",
            severity="sev1",
        ),
        actor_user_id=actor_user_id,
    )
    return output
