"""Planned and roadmap integrations for IncidentPilot."""

from __future__ import annotations

from typing import Any

from app.integrations.base import (
    BaseIntegrationClient,
    IntegrationProvider,
    IntegrationStatus,
    PlannedIntegrationError,
    ProviderMetadata,
)

# Registry of all MVP and Planned Integrations
INTEGRATION_REGISTRY: list[ProviderMetadata] = [
    ProviderMetadata(
        provider=IntegrationProvider.SLACK,
        display_name="Slack War Room",
        status=IntegrationStatus.ACTIVE,
        category="Communication",
        description="Broadcast incident status updates, manage war room channels, and share AI co-commander debriefs.",
        supported_operations=["post_broadcast", "create_channel", "post_debrief"],
        is_planned=False,
    ),
    ProviderMetadata(
        provider=IntegrationProvider.JIRA,
        display_name="Jira Incident Tracker",
        status=IntegrationStatus.ACTIVE,
        category="Issue Tracking",
        description="Create tracking tickets, sync incident metadata, and link remediation action items.",
        supported_operations=["create_ticket", "link_action_item"],
        is_planned=False,
    ),
    ProviderMetadata(
        provider=IntegrationProvider.MONITORING,
        display_name="Monitoring Telemetry (Datadog/CloudWatch)",
        status=IntegrationStatus.ACTIVE,
        category="Observability",
        description="Read-only telemetry queries (error rates, p99 latency, saturation) and alert ingestion.",
        supported_operations=["fetch_health", "fetch_alerts"],
        is_planned=False,
    ),
    ProviderMetadata(
        provider=IntegrationProvider.PAGERDUTY,
        display_name="PagerDuty On-Call",
        status=IntegrationStatus.PLANNED,
        category="On-Call & Escalation",
        description="Trigger and acknowledge on-call responder pages and escalation policies.",
        supported_operations=["trigger_page", "ack_incident", "resolve_incident"],
        is_planned=True,
        roadmap_milestone="v0.3-GA",
    ),
    ProviderMetadata(
        provider=IntegrationProvider.GITHUB,
        display_name="GitHub Deployments & Issues",
        status=IntegrationStatus.PLANNED,
        category="Source & CI/CD",
        description="Correlate commit SHAs, pull request merges, and deployment events to active incidents.",
        supported_operations=["query_deployments", "create_postmortem_issue"],
        is_planned=True,
        roadmap_milestone="v0.3-GA",
    ),
    ProviderMetadata(
        provider=IntegrationProvider.OPSGENIE,
        display_name="Opsgenie Alerting",
        status=IntegrationStatus.PLANNED,
        category="On-Call & Escalation",
        description="Multi-tier team paging and alert deduplication.",
        supported_operations=["create_alert", "ack_alert"],
        is_planned=True,
        roadmap_milestone="v0.4-LTS",
    ),
]


class PlannedIntegrationStub(BaseIntegrationClient):
    """Stub client for planned integrations that explicitly raises PlannedIntegrationError."""

    def __init__(self, provider: IntegrationProvider, roadmap_milestone: str = "v0.3-GA"):
        super().__init__(provider=provider)
        self.roadmap_milestone = roadmap_milestone

    async def execute_planned_operation(self, operation_name: str, payload: dict[str, Any] | None = None) -> Any:
        raise PlannedIntegrationError(provider=self.provider.value, roadmap_milestone=self.roadmap_milestone)
