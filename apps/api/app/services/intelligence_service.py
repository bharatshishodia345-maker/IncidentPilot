"""Intelligence domain service coordinating transcript analysis, validation, and audit events."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.provider import AIProvider, get_ai_provider
from app.ai.schemas import (
    AnalysisRequest,
    IncidentIntelligenceOutput,
    TranscriptMessage,
)
from app.db.models import AuditActorType
from app.services.audit import AuditService
from app.services.incident_service import IncidentService


class IntelligenceService:
    """Encapsulates incident intelligence extraction with safety validations and audit trails."""

    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or get_ai_provider()

    async def analyze_incident_stream(
        self,
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        request: AnalysisRequest,
        actor_user_id: UUID | None = None,
    ) -> IncidentIntelligenceOutput:
        """Process conversation and telemetry stream through the isolated AI provider with validation."""
        # 1. Enforce multi-tenancy access check
        incident = IncidentService.get_incident(session, organization_id, incident_id)

        # Context enrichment
        if request.incident_title is None:
            request.incident_title = incident.title
        if request.severity is None:
            request.severity = incident.severity.value

        # 2. Invoke the pluggable AI provider
        intelligence = await self.provider.analyze(request)

        # 3. Validation and Safety Safeguards:
        # Guarantee: No unassigned action has a hallucinated owner
        for action in intelligence.actions:
            if action.assigned_owner and action.assigned_owner.lower() in {"ai", "system", "bot", "assistant"}:
                action.assigned_owner = None

        # 4. Record append-only audit event for AI extraction
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.AI,
            event_type="incident.intelligence_analyzed",
            payload={
                "incident_id": str(incident_id),
                "messages_count": len(request.messages),
                "facts_count": len(intelligence.facts),
                "hypotheses_count": len(intelligence.hypotheses),
                "decisions_count": len(intelligence.decisions),
                "actions_count": len(intelligence.actions),
                "conflicts_count": len(intelligence.conflicts),
                "unknowns_count": len(intelligence.unknowns),
                "summary": intelligence.summary,
            },
            incident_id=incident_id,
            actor_user_id=actor_user_id,
        )
        session.commit()

        return intelligence
