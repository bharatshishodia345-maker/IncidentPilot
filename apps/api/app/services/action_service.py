"""Domain service for human-in-the-loop remediation proposal, authorization, and execution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actions.executors import SandboxedActionExecutor
from app.actions.schemas import (
    ActionProposalCreate,
    AllowlistedActionType,
    ProposalStatus,
    RiskLevel,
)
from app.core.exceptions import (
    ConflictError,
    EntityNotFoundError,
    PermissionDeniedError,
)
from app.db.models import (
    ActionProposal,
    AuditActorType,
    TimelineEvent,
    TimelineEventType,
    User,
    UserRole,
)
from app.services.audit import AuditService
from app.services.incident_service import IncidentService


class ActionService:
    """Encapsulates secure human-in-the-loop action workflows with replay and expiry protection."""

    @staticmethod
    def propose_action(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        payload: ActionProposalCreate,
        actor_type: AuditActorType = AuditActorType.AI,
        actor_user_id: UUID | None = None,
    ) -> ActionProposal:
        """Create a pending action proposal that requires human commander authorization."""
        IncidentService.get_incident(session, organization_id, incident_id)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=payload.expires_in_minutes)
        idempotency_key = f"{incident_id}-{payload.action_type.value}-{uuid4().hex[:12]}"

        proposal = ActionProposal(
            incident_id=incident_id,
            organization_id=organization_id,
            action_type=payload.action_type.value,
            title=payload.title,
            description=payload.description,
            parameters=payload.parameters,
            risk_level=payload.risk_level.value,
            status=ProposalStatus.PENDING_APPROVAL.value,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            proposed_by_actor_type=actor_type,
            proposed_by_user_id=actor_user_id,
        )
        session.add(proposal)
        session.flush()

        # Audit event for proposal creation
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=actor_type,
            event_type="incident.action_proposed",
            payload={
                "proposal_id": str(proposal.id),
                "action_type": proposal.action_type,
                "title": proposal.title,
                "risk_level": proposal.risk_level,
                "expires_at": expires_at.isoformat(),
            },
            incident_id=incident_id,
            actor_user_id=actor_user_id,
        )

        session.commit()
        session.refresh(proposal)
        return proposal

    @staticmethod
    def approve_and_execute_action(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        proposal_id: UUID,
        approver_user_id: UUID,
        approver_role: UserRole,
        rationale: str | None = None,
    ) -> ActionProposal:
        """Authorize and atomically execute an allowlisted action with replay and expiry protection."""
        proposal = ActionService.get_proposal(session, organization_id, incident_id, proposal_id)

        # 1. RBAC & Least Privilege Check: Only Incident Commander can authorize
        if approver_role != UserRole.INCIDENT_COMMANDER:
            raise PermissionDeniedError("Only Incident Commanders can authorize consequential remediation actions.")

        # 2. Replay Protection: Must be in PENDING_APPROVAL status
        if proposal.status != ProposalStatus.PENDING_APPROVAL.value:
            raise ConflictError(
                f"Action proposal cannot be approved in '{proposal.status}' state (must be '{ProposalStatus.PENDING_APPROVAL.value}'). Duplicate approval or replay blocked."
            )

        now = datetime.now(timezone.utc)
        expires_at = proposal.expires_at if proposal.expires_at.tzinfo is not None else proposal.expires_at.replace(tzinfo=timezone.utc)

        # 3. Expiry Protection: Proposal must not have expired
        if now > expires_at:
            proposal.status = ProposalStatus.EXPIRED.value
            session.commit()
            raise ConflictError("Action proposal has expired and cannot be authorized. A fresh proposal must be created.")


        # 4. Mark Approved & Dispatch Sandboxed Execution
        proposal.status = ProposalStatus.APPROVED.value
        proposal.approved_by_user_id = approver_user_id
        proposal.approved_at = now
        session.flush()

        # Log authorization audit event
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER,
            event_type="incident.action_approved",
            payload={
                "proposal_id": str(proposal.id),
                "action_type": proposal.action_type,
                "approved_by": str(approver_user_id),
                "rationale": rationale or "Authorized in war room",
            },
            incident_id=incident_id,
            actor_user_id=approver_user_id,
        )

        try:
            # 5. Execute Sandboxed Allowlisted Action
            execution_receipt = SandboxedActionExecutor.execute(
                action_type=AllowlistedActionType(proposal.action_type),
                parameters=proposal.parameters,
                incident_id=str(incident_id),
                organization_id=str(organization_id),
            )
            proposal.status = ProposalStatus.EXECUTED.value
            proposal.executed_at = datetime.now(timezone.utc)
            proposal.execution_result = execution_receipt
        except Exception as exc:
            proposal.status = ProposalStatus.FAILED.value
            proposal.execution_result = {"status": "failed", "error": str(exc)}

        # 6. Append Timeline Event
        timeline_event = TimelineEvent(
            incident_id=incident_id,
            event_type=TimelineEventType.ACTION,
            title=f"Remediation Executed: {proposal.title}",
            details=f"Authorized by Commander with status '{proposal.status}'.",
            created_by_user_id=approver_user_id,
        )
        session.add(timeline_event)

        # 7. Append Execution Audit Record
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.SYSTEM,
            event_type="incident.action_executed",
            payload={
                "proposal_id": str(proposal.id),
                "action_type": proposal.action_type,
                "execution_status": proposal.status,
                "execution_result": proposal.execution_result,
            },
            incident_id=incident_id,
            actor_user_id=approver_user_id,
        )

        session.commit()
        session.refresh(proposal)
        return proposal

    @staticmethod
    def reject_action(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        proposal_id: UUID,
        rejecter_user_id: UUID,
        rejecter_role: UserRole,
        reason: str,
    ) -> ActionProposal:
        """Reject an action proposal, updating state and recording audit event."""
        proposal = ActionService.get_proposal(session, organization_id, incident_id, proposal_id)

        if rejecter_role not in {UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER}:
            raise PermissionDeniedError("Observers cannot reject action proposals.")

        if proposal.status != ProposalStatus.PENDING_APPROVAL.value:
            raise ConflictError(f"Action proposal cannot be rejected in '{proposal.status}' state.")

        proposal.status = ProposalStatus.REJECTED.value
        proposal.rejection_reason = reason

        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER,
            event_type="incident.action_rejected",
            payload={
                "proposal_id": str(proposal.id),
                "action_type": proposal.action_type,
                "rejection_reason": reason,
                "rejected_by": str(rejecter_user_id),
            },
            incident_id=incident_id,
            actor_user_id=rejecter_user_id,
        )

        session.commit()
        session.refresh(proposal)
        return proposal

    @staticmethod
    def get_proposal(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        proposal_id: UUID,
    ) -> ActionProposal:
        """Fetch proposal strictly scoped to the incident and tenant organization."""
        IncidentService.get_incident(session, organization_id, incident_id)

        statement = select(ActionProposal).where(
            ActionProposal.id == proposal_id,
            ActionProposal.incident_id == incident_id,
            ActionProposal.organization_id == organization_id,
        )
        proposal = session.scalar(statement)
        if proposal is None:
            raise EntityNotFoundError("ActionProposal", str(proposal_id))
        return proposal

    @staticmethod
    def list_proposals(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        status: str | None = None,
    ) -> list[ActionProposal]:
        """List action proposals for an incident."""
        IncidentService.get_incident(session, organization_id, incident_id)

        statement = select(ActionProposal).where(
            ActionProposal.incident_id == incident_id,
            ActionProposal.organization_id == organization_id,
        )
        if status:
            statement = statement.where(ActionProposal.status == status)

        statement = statement.order_by(ActionProposal.created_at.desc())
        return list(session.scalars(statement).all())
