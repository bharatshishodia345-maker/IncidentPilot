"""REST endpoints for human-in-the-loop action proposals, approvals, and sandboxed execution."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actions.schemas import (
    ActionApprovalRequest,
    ActionProposalCreate,
    ActionProposalDetail,
    ActionRejectionRequest,
)
from app.auth.dependencies import Principal, get_current_principal, require_roles
from app.core.exceptions import EntityNotFoundError
from app.db.models import AuditActorType, User, UserRole
from app.db.session import get_db
from app.services.action_service import ActionService

router = APIRouter(tags=["actions"])


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
    "/incidents/{incident_id}/actions/propose",
    response_model=ActionProposalDetail,
    status_code=status.HTTP_201_CREATED,
)
def propose_remediation_action(
    incident_id: UUID,
    payload: ActionProposalCreate,
    principal: Principal = Depends(require_roles(UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER)),
    session: Session = Depends(get_db),
) -> ActionProposalDetail:
    """Propose an allowlisted remediation action requiring human approval."""
    actor_user_id = _resolve_user_id(session, principal)
    actor_type = AuditActorType.USER

    proposal = ActionService.propose_action(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        payload=payload,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
    )
    return ActionProposalDetail.model_validate(proposal)


@router.get("/incidents/{incident_id}/actions/proposals", response_model=list[ActionProposalDetail])
def list_action_proposals(
    incident_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> list[ActionProposalDetail]:
    """List all remediation proposals for an incident."""
    proposals = ActionService.list_proposals(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        status=status_filter,
    )
    return [ActionProposalDetail.model_validate(p) for p in proposals]


@router.get("/incidents/{incident_id}/actions/proposals/{proposal_id}", response_model=ActionProposalDetail)
def get_action_proposal(
    incident_id: UUID,
    proposal_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> ActionProposalDetail:
    """Fetch details and execution receipt for a specific remediation proposal."""
    proposal = ActionService.get_proposal(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        proposal_id=proposal_id,
    )
    return ActionProposalDetail.model_validate(proposal)


@router.post(
    "/incidents/{incident_id}/actions/proposals/{proposal_id}/approve",
    response_model=ActionProposalDetail,
)
def approve_and_execute_action(
    incident_id: UUID,
    proposal_id: UUID,
    payload: ActionApprovalRequest | None = None,
    principal: Principal = Depends(require_roles(UserRole.INCIDENT_COMMANDER)),
    session: Session = Depends(get_db),
) -> ActionProposalDetail:
    """Authorize and execute a remediation action (Restricted to Incident Commanders)."""
    approver_user_id = _resolve_user_id(session, principal)
    rationale = payload.rationale if payload else None

    proposal = ActionService.approve_and_execute_action(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        proposal_id=proposal_id,
        approver_user_id=approver_user_id,
        approver_role=principal.role,
        rationale=rationale,
    )
    return ActionProposalDetail.model_validate(proposal)


@router.post(
    "/incidents/{incident_id}/actions/proposals/{proposal_id}/reject",
    response_model=ActionProposalDetail,
)
def reject_action_proposal(
    incident_id: UUID,
    proposal_id: UUID,
    payload: ActionRejectionRequest,
    principal: Principal = Depends(require_roles(UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER)),
    session: Session = Depends(get_db),
) -> ActionProposalDetail:
    """Reject a proposed remediation action."""
    rejecter_user_id = _resolve_user_id(session, principal)

    proposal = ActionService.reject_action(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        proposal_id=proposal_id,
        rejecter_user_id=rejecter_user_id,
        rejecter_role=principal.role,
        reason=payload.reason,
    )
    return ActionProposalDetail.model_validate(proposal)
