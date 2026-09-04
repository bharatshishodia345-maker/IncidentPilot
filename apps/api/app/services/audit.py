"""Audit event persistence service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditActorType, AuditEvent


class AuditService:
    """Provides append-only audit event logging across all domain services."""

    @staticmethod
    def record_event(
        session: Session,
        organization_id: UUID,
        actor_type: AuditActorType,
        event_type: str,
        payload: dict[str, Any] | None = None,
        incident_id: UUID | None = None,
        actor_user_id: UUID | None = None,
    ) -> AuditEvent:
        """Create and stage an append-only audit event within the active session transaction."""
        audit_event = AuditEvent(
            organization_id=organization_id,
            incident_id=incident_id,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            event_type=event_type,
            payload=payload or {},
        )
        session.add(audit_event)
        return audit_event
