"""External incident tools integration subsystem."""

from app.integrations.base import (
    BaseIntegrationClient,
    IntegrationAuthError,
    IntegrationError,
    IntegrationNetworkError,
    IntegrationProvider,
    IntegrationRateLimitError,
    IntegrationStatus,
    IntegrationTimeoutError,
    PlannedIntegrationError,
    ProviderMetadata,
)
from app.integrations.jira import (
    JiraActionLinkPayload,
    JiraIntegrationClient,
    JiraTicketCreatePayload,
    JiraTicketResponse,
)
from app.integrations.monitoring import (
    MonitoringAlertItem,
    MonitoringIntegrationClient,
    ServiceHealthMetrics,
)
from app.integrations.planned import (
    INTEGRATION_REGISTRY,
    PlannedIntegrationStub,
)
from app.integrations.slack import (
    SlackBroadcastPayload,
    SlackBroadcastResponse,
    SlackChannelResponse,
    SlackIntegrationClient,
)

__all__ = [
    "BaseIntegrationClient",
    "IntegrationProvider",
    "IntegrationStatus",
    "ProviderMetadata",
    "IntegrationError",
    "IntegrationAuthError",
    "IntegrationRateLimitError",
    "IntegrationTimeoutError",
    "IntegrationNetworkError",
    "PlannedIntegrationError",
    "SlackBroadcastPayload",
    "SlackBroadcastResponse",
    "SlackChannelResponse",
    "SlackIntegrationClient",
    "JiraTicketCreatePayload",
    "JiraTicketResponse",
    "JiraActionLinkPayload",
    "JiraIntegrationClient",
    "ServiceHealthMetrics",
    "MonitoringAlertItem",
    "MonitoringIntegrationClient",
    "INTEGRATION_REGISTRY",
    "PlannedIntegrationStub",
]
