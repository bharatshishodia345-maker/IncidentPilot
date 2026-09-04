"""REST endpoints for verified-feedback learning layer and organization knowledge base."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Principal, get_current_principal, require_roles
from app.core.exceptions import EntityNotFoundError
from app.db.models import User, UserRole
from app.db.session import get_db
from app.learning.schemas import (
    HistoricalContextItem,
    KnowledgeRecordDetail,
    OutcomeValidationRequest,
)
from app.services.learning_service import LearningService

router = APIRouter(tags=["learnings"])


def _resolve_user_id(session: Session, principal: Principal) -> UUID:
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
    "/incidents/{incident_id}/learnings/validate",
    response_model=KnowledgeRecordDetail,
    status_code=status.HTTP_201_CREATED,
)
def validate_incident_outcome(
    incident_id: UUID,
    payload: OutcomeValidationRequest,
    principal: Principal = Depends(require_roles(UserRole.INCIDENT_COMMANDER)),
    session: Session = Depends(get_db),
) -> KnowledgeRecordDetail:
    """Validate and commit post-incident verified outcome (Restricted to Incident Commanders)."""
    validator_user_id = _resolve_user_id(session, principal)

    record = LearningService.validate_and_record_outcome(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        validator_user_id=validator_user_id,
        validator_role=principal.role,
        payload=payload,
    )
    return KnowledgeRecordDetail.model_validate(record)


@router.get(
    "/incidents/{incident_id}/learnings/relevant",
    response_model=list[HistoricalContextItem],
)
def get_relevant_historical_context(
    incident_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> list[HistoricalContextItem]:
    """Retrieve verified historical outcomes from previous incidents in the organization."""
    return LearningService.build_historical_context_for_incident(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
    )


@router.get("/learnings", response_model=list[KnowledgeRecordDetail])
def search_knowledge_base(
    query: str | None = Query(None, description="Search query keywords in summary/root-cause"),
    tags: list[str] | None = Query(None, description="Filter by tags"),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> list[KnowledgeRecordDetail]:
    """Search the organization's verified knowledge base."""
    records = LearningService.retrieve_relevant_knowledge(
        session=session,
        organization_id=principal.organization_id,
        query_text=query,
        tags=tags,
    )
    return [KnowledgeRecordDetail.model_validate(r) for r in records]
