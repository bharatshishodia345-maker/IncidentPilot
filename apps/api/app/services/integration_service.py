"""Domain service orchestrating external incident integrations and audit logging."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditActorType, TimelineEvent, TimelineEventType, UserRole
from app.integrations.base import IntegrationProvider, PlannedIntegrationError
from app.integrations.jira import (
    JiraIntegrationClient,
    JiraTicketCreatePayload,
    JiraTicketResponse,
)
from app.integrations.monitoring import (
    MonitoringIntegrationClient,
    ServiceHealthMetrics,
)
from app.integrations.planned import PlannedIntegrationStub
from app.integrations.slack import (
    SlackBroadcastPayload,
    SlackBroadcastResponse,
    SlackIntegrationClient,
)
from app.services.audit import AuditService
from app.services.incident_service import IncidentService


class IntegrationService:
    """Handles external integration dispatches, tenant validation, and audit recording."""

    @staticmethod
    async def broadcast_to_slack(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        payload: SlackBroadcastPayload,
        actor_user_id: UUID,
    ) -> SlackBroadcastResponse:
        """Broadcast incident status to Slack with multi-tenant verification and audit logging."""
        incident = IncidentService.get_incident(session, organization_id, incident_id)

        client = SlackIntegrationClient()
        response = await client.post_incident_broadcast(payload)

        # 1. Audit Log
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER,
            event_type="integration.slack.broadcast",
            payload={
                "channel": payload.channel,
                "title": payload.title,
                "message_ts": response.message_ts,
                "permalink": response.permalink,
            },
            incident_id=incident_id,
            actor_user_id=actor_user_id,
        )

        # 2. Timeline Event
        timeline_event = TimelineEvent(
            incident_id=incident_id,
            event_type=TimelineEventType.NOTE,
            title=f"Broadcast to Slack ({payload.channel})",
            details=f"Posted update: {payload.title}",
            created_by_user_id=actor_user_id,
        )
        session.add(timeline_event)
        session.commit()

        return response

    @staticmethod
    async def create_jira_ticket(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        payload: JiraTicketCreatePayload,
        actor_user_id: UUID,
    ) -> JiraTicketResponse:
        """Create an incident tracking ticket in Jira and link to timeline."""
        incident = IncidentService.get_incident(session, organization_id, incident_id)

        client = JiraIntegrationClient()
        response = await client.create_incident_ticket(payload)

        # 1. Audit Log
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER,
            event_type="integration.jira.ticket_created",
            payload={
                "issue_key": response.issue_key,
                "issue_url": response.issue_url,
                "summary": payload.summary,
                "project_key": payload.project_key,
            },
            incident_id=incident_id,
            actor_user_id=actor_user_id,
        )

        # 2. Timeline Event
        timeline_event = TimelineEvent(
            incident_id=incident_id,
            event_type=TimelineEventType.NOTE,
            title=f"Jira Issue Created: {response.issue_key}",
            details=f"Tracking issue created at {response.issue_url}",
            created_by_user_id=actor_user_id,
        )
        session.add(timeline_event)
        session.commit()

        return response

    @staticmethod
    async def query_monitoring_health(
        session: Session,
        organization_id: UUID,
        incident_id: UUID,
        service_name: str,
        actor_user_id: UUID | None = None,
    ) -> ServiceHealthMetrics:
        """Execute read-only query for service telemetry and record query audit event."""
        incident = IncidentService.get_incident(session, organization_id, incident_id)

        client = MonitoringIntegrationClient()
        metrics = await client.fetch_service_health(service_name)

        # Audit Log (Read-only query audit)
        AuditService.record_event(
            session=session,
            organization_id=organization_id,
            actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
            event_type="integration.monitoring.health_queried",
            payload={
                "service_name": service_name,
                "status": metrics.status,
                "error_rate": metrics.error_rate_percent,
                "p99_latency_ms": metrics.p99_latency_ms,
            },
            incident_id=incident_id,
            actor_user_id=actor_user_id,
        )
        session.commit()

        return metrics

    @staticmethod
    def dispatch_planned_integration(
        provider_name: str,
    ) -> None:
        """Raise structured PlannedIntegrationError for roadmap providers."""
        try:
            prov = IntegrationProvider(provider_name.lower())
        except ValueError:
            raise PlannedIntegrationError(provider=provider_name)
        stub = PlannedIntegrationStub(provider=prov)
        raise PlannedIntegrationError(provider=prov.value, roadmap_milestone=stub.roadmap_milestone)
