"""Tenant-scoped incident endpoints utilizing IncidentService."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    IncidentCreate,
    IncidentDetail,
    IncidentStatusUpdate,
    IncidentSummary,
)
from app.auth.dependencies import Principal, get_current_principal, require_roles
from app.core.exceptions import EntityNotFoundError
from app.db.models import IncidentSeverity, IncidentStatus, User, UserRole
from app.db.session import get_db
from app.services.incident_service import IncidentService

router = APIRouter(tags=["incidents"])


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


@router.get("/incidents", response_model=list[IncidentSummary])
def list_incidents(
    status_filter: IncidentStatus | None = Query(None, alias="status"),
    severity_filter: IncidentSeverity | None = Query(None, alias="severity"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> list[IncidentSummary]:
    """List incidents strictly inside the principal's organization with optional filters."""
    incidents = IncidentService.list_incidents(
        session=session,
        organization_id=principal.organization_id,
        status=status_filter,
        severity=severity_filter,
        limit=limit,
        offset=offset,
    )
    return [IncidentSummary.model_validate(inc) for inc in incidents]


@router.post("/incidents", response_model=IncidentDetail, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    principal: Principal = Depends(require_roles(UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER)),
    session: Session = Depends(get_db),
) -> IncidentDetail:
    """Declare a new incident within the principal's organization."""
    actor_user_id = _resolve_user_id(session, principal)
    commander_id = payload.commander_user_id or actor_user_id

    incident = IncidentService.create_incident(
        session=session,
        organization_id=principal.organization_id,
        commander_user_id=commander_id,
        title=payload.title,
        severity=payload.severity,
        status=payload.status,
        actor_user_id=actor_user_id,
    )
    return IncidentDetail.model_validate(incident)


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def get_incident(
    incident_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> IncidentDetail:
    """Get details for a specific incident scoped to the principal's organization."""
    incident = IncidentService.get_incident(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
    )
    return IncidentDetail.model_validate(incident)


@router.patch("/incidents/{incident_id}/status", response_model=IncidentDetail)
def update_incident_status(
    incident_id: UUID,
    payload: IncidentStatusUpdate,
    principal: Principal = Depends(require_roles(UserRole.INCIDENT_COMMANDER)),
    session: Session = Depends(get_db),
) -> IncidentDetail:
    """Transition an incident's lifecycle status (restricted to Incident Commanders)."""
    actor_user_id = _resolve_user_id(session, principal)

    incident = IncidentService.update_incident_status(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        new_status=payload.status,
        actor_user_id=actor_user_id,
    )
    return IncidentDetail.model_validate(incident)
