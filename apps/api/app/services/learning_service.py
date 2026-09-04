"""Domain service for verified-feedback learning layer and organization knowledge base."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, EntityNotFoundError, PermissionDeniedError
from app.db.models import AuditActorType, Incident, IncidentStatus, KnowledgeRecord, UserRole
from app.learning.schemas import (
    HistoricalContextItem,
    KnowledgeRecordDetail,
    OutcomeValidationRequest,
)
from app.services.audit import AuditService
from app.services.incident_service import IncidentService


class LearningService:
    """Manages verified outcome validation and organization-scoped historical knowledge retrieval.

    Principles:
    - Never automatically retrains AI models.
    - Historical knowledge is NEVER a current fact.
    - Only human-validated outcomes on resolved/mitigated incidents enter the knowledge base.
    """

    @staticmethod
    def validate_and_record_outcome(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        validator_user_id: UUID,
        validator_role: UserRole,
        payload: OutcomeValidationRequest,
    ) -> KnowledgeRecord:
        """Validate and record an official post-incident outcome into the organization knowledge base."""
        incident = IncidentService.get_incident(session, organization_id, incident_id)

        # 1. RBAC Check: Only Incident Commander can validate outcomes
        if validator_role != UserRole.INCIDENT_COMMANDER:
            raise PermissionDeniedError("Only Incident Commanders can validate and commit post-incident verified outcomes.")

        # 2. Lifecycle Check: Unresolved incidents cannot be committed as verified knowledge
        allowed_statuses = {IncidentStatus.RESOLVED, IncidentStatus.MITIGATED}
        if incident.status not in allowed_statuses:
            raise ConflictError(
                f"Cannot validate outcome for incident in '{incident.status.value}' state. Incident must be mitigated or resolved."
            )


        now = datetime.now(timezone.utc)

        # 3. Check for existing record
        existing = session.scalar(
            select(KnowledgeRecord).where(
                KnowledgeRecord.incident_id == incident_id,
                KnowledgeRecord.organization_id == organization_id,
            )
        )

        if existing is not None:
            existing.summary = payload.summary
            existing.root_cause = payload.root_cause
            existing.effective_remediation = payload.effective_remediation
            existing.preventative_actions = payload.preventative_actions
            existing.tags = payload.tags
            existing.validated_by_user_id = validator_user_id
            existing.validated_at = now
            record = existing
        else:
            record = KnowledgeRecord(
                organization_id=organization_id,
                incident_id=incident_id,
                summary=payload.summary,
                root_cause=payload.root_cause,
                effective_remediation=payload.effective_remediation,
                preventative_actions=payload.preventative_actions,
                tags=payload.tags,
                validated_by_user_id=validator_user_id,
                validated_at=now,
            )
            session.add(record)

        session.flush()

        # 4. Audit Log
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER,
            event_type="learning.outcome_validated",
            payload={
                "knowledge_record_id": str(record.id),
                "incident_id": str(incident_id),
                "validated_by": str(validator_user_id),
                "tags": payload.tags,
            },
            incident_id=incident_id,
            actor_user_id=validator_user_id,
        )

        session.commit()
        session.refresh(record)
        return record

    @staticmethod
    def retrieve_relevant_knowledge(
        session: Session,
        organization_id: UUID,
        query_text: str | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[KnowledgeRecord]:
        """Retrieve historical knowledge records strictly scoped to the tenant organization."""
        statement = select(KnowledgeRecord).where(KnowledgeRecord.organization_id == organization_id)

        records = list(session.scalars(statement.order_by(KnowledgeRecord.validated_at.desc())).all())

        if not query_text and not tags:
            return records[:limit]

        query_lower = query_text.lower() if query_text else ""
        filter_tags = set(t.lower() for t in tags) if tags else set()

        def match_score(rec: KnowledgeRecord) -> int:
            score = 0
            if filter_tags:
                rec_tags = set(t.lower() for t in rec.tags)
                score += len(filter_tags.intersection(rec_tags)) * 2

            if query_lower:
                if query_lower in rec.summary.lower():
                    score += 1
                if query_lower in rec.root_cause.lower():
                    score += 2
                if query_lower in rec.effective_remediation.lower():
                    score += 1
            return score

        matched = [r for r in records if match_score(r) > 0]
        matched.sort(key=match_score, reverse=True)
        return (matched if matched else records)[:limit]

    @staticmethod
    def build_historical_context_for_incident(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
    ) -> list[HistoricalContextItem]:
        """Fetch historical verified outcomes for an active incident, excluding itself."""
        current_incident = IncidentService.get_incident(session, organization_id, incident_id)

        # Retrieve records from other incidents in same org
        statement = (
            select(KnowledgeRecord)
            .where(
                KnowledgeRecord.organization_id == organization_id,
                KnowledgeRecord.incident_id != incident_id,
            )
            .order_by(KnowledgeRecord.validated_at.desc())
            .limit(5)
        )
        records = list(session.scalars(statement).all())

        items: list[HistoricalContextItem] = []
        for rec in records:
            inc_title = rec.incident.title if rec.incident else "Historical Incident"
            items.append(
                HistoricalContextItem(
                    record_id=rec.id,
                    incident_title=inc_title,
                    verified_root_cause=rec.root_cause,
                    effective_remediation=rec.effective_remediation,
                    tags=rec.tags,
                )
            )
        return items
