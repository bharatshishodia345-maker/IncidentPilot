"""REST endpoints for external incident tool integrations."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Principal, get_current_principal, require_roles
from app.core.exceptions import EntityNotFoundError
from app.db.models import User, UserRole
from app.db.session import get_db
from app.integrations.base import ProviderMetadata
from app.integrations.jira import JiraTicketCreatePayload, JiraTicketResponse
from app.integrations.monitoring import ServiceHealthMetrics
from app.integrations.planned import INTEGRATION_REGISTRY
from app.integrations.slack import SlackBroadcastPayload, SlackBroadcastResponse
from app.services.integration_service import IntegrationService

router = APIRouter(tags=["integrations"])


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


@router.get("/integrations/providers", response_model=list[ProviderMetadata])
def list_integration_providers() -> list[ProviderMetadata]:
    """List all supported MVP and planned roadmap integration providers."""
    return INTEGRATION_REGISTRY


@router.post(
    "/incidents/{incident_id}/integrations/slack/broadcast",
    response_model=SlackBroadcastResponse,
    status_code=status.HTTP_200_OK,
)
async def broadcast_to_slack(
    incident_id: UUID,
    payload: SlackBroadcastPayload,
    principal: Principal = Depends(require_roles(UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER)),
    session: Session = Depends(get_db),
) -> SlackBroadcastResponse:
    """Broadcast an incident status update to a Slack channel."""
    actor_user_id = _resolve_user_id(session, principal)
    return await IntegrationService.broadcast_to_slack(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        payload=payload,
        actor_user_id=actor_user_id,
    )


@router.post(
    "/incidents/{incident_id}/integrations/jira/ticket",
    response_model=JiraTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_jira_ticket(
    incident_id: UUID,
    payload: JiraTicketCreatePayload,
    principal: Principal = Depends(require_roles(UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER)),
    session: Session = Depends(get_db),
) -> JiraTicketResponse:
    """Create a tracking ticket in Jira for the active incident."""
    actor_user_id = _resolve_user_id(session, principal)
    return await IntegrationService.create_jira_ticket(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        payload=payload,
        actor_user_id=actor_user_id,
    )


@router.get(
    "/incidents/{incident_id}/integrations/monitoring/metrics",
    response_model=ServiceHealthMetrics,
)
async def query_monitoring_health(
    incident_id: UUID,
    service_name: str = Query(..., description="Name of the service to query telemetry for"),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> ServiceHealthMetrics:
    """Query live read-only telemetry metrics from monitoring provider."""
    actor_user_id = _resolve_user_id(session, principal) if principal.user_id else None
    return await IntegrationService.query_monitoring_health(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        service_name=service_name,
        actor_user_id=actor_user_id,
    )


@router.post(
    "/incidents/{incident_id}/integrations/planned/{provider_name}",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def trigger_planned_integration(
    incident_id: UUID,
    provider_name: str,
    principal: Principal = Depends(get_current_principal),
) -> None:
    """Stub endpoint for planned future integrations."""
    IntegrationService.dispatch_planned_integration(provider_name=provider_name)
