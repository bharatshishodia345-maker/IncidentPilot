"""Base integration client, provider registry, error hierarchy, and retry engine."""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, Field

from app.core.exceptions import IncidentPilotException


class IntegrationProvider(str, Enum):
    """External incident tool integration providers."""

    SLACK = "slack"
    JIRA = "jira"
    MONITORING = "monitoring"
    PAGERDUTY = "pagerduty"
    GITHUB = "github"
    OPSGENIE = "opsgenie"


class IntegrationStatus(str, Enum):
    """Status of an integration provider."""

    ACTIVE = "active"
    CONFIGURED = "configured"
    UNCONFIGURED = "unconfigured"
    PLANNED = "planned"


class ProviderMetadata(BaseModel):
    """Metadata descriptor for an integration provider."""

    provider: IntegrationProvider
    display_name: str
    status: IntegrationStatus
    category: str
    description: str
    supported_operations: list[str]
    is_planned: bool = False
    roadmap_milestone: str | None = None


# Structured Exception Hierarchy
class IntegrationError(IncidentPilotException):
    """Base exception for all external integration failures."""

    def __init__(self, provider: str, message: str, status_code: int = 502, code: str = "INTEGRATION_ERROR"):
        super().__init__(f"[{provider.upper()}] {message}")
        self.provider = provider
        self.status_code = status_code
        self.code = code



class IntegrationAuthError(IntegrationError):
    """Authentication or credential failure when connecting to external service."""

    def __init__(self, provider: str, message: str = "External service authentication failed"):
        super().__init__(provider=provider, message=message, status_code=502, code="INTEGRATION_AUTH_ERROR")


class IntegrationRateLimitError(IntegrationError):
    """Rate limit (HTTP 429) encountered from external provider."""

    def __init__(self, provider: str, retry_after: int | None = None):
        msg = f"External API rate limit reached. Retry after {retry_after}s" if retry_after else "Rate limit reached"
        super().__init__(provider=provider, message=msg, status_code=503, code="INTEGRATION_RATE_LIMIT")
        self.retry_after = retry_after


class IntegrationTimeoutError(IntegrationError):
    """Timeout exceeded when contacting external provider."""

    def __init__(self, provider: str, timeout_seconds: float):
        super().__init__(
            provider=provider,
            message=f"Request timed out after {timeout_seconds}s",
            status_code=504,
            code="INTEGRATION_TIMEOUT",
        )
        self.timeout_seconds = timeout_seconds


class IntegrationNetworkError(IntegrationError):
    """Network transport or connection failure."""

    def __init__(self, provider: str, message: str):
        super().__init__(provider=provider, message=f"Network failure: {message}", status_code=502, code="INTEGRATION_NETWORK_ERROR")


class PlannedIntegrationError(IntegrationError):
    """Raised when an operation is requested on a planned, non-MVP integration."""

    def __init__(self, provider: str, roadmap_milestone: str = "v0.3-GA"):
        super().__init__(
            provider=provider,
            message=f"Integration with '{provider}' is planned for {roadmap_milestone} and not yet enabled in the MVP.",
            status_code=501,
            code="INTEGRATION_PLANNED",
        )


T = TypeVar("T")


class BaseIntegrationClient:
    """Base client providing robust async timeouts, exponential backoff retries, and error isolation."""

    def __init__(
        self,
        provider: IntegrationProvider,
        timeout_seconds: float = 5.0,
        max_retries: int = 3,
        backoff_base: float = 0.05,
    ):
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    async def execute_with_resilience(
        self,
        operation_name: str,
        coroutine_factory: Callable[[], Any],
    ) -> Any:
        """Execute an external operation with strict timeout and exponential backoff retry bounds."""
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Wrap each attempt in an asyncio timeout
                return await asyncio.wait_for(
                    coroutine_factory(),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                last_error = IntegrationTimeoutError(self.provider.value, self.timeout_seconds)
                if attempt == self.max_retries:
                    raise last_error from exc
            except IntegrationError as exc:
                last_error = exc
                # Do not retry 401/403 auth errors or planned errors
                if isinstance(exc, (IntegrationAuthError, PlannedIntegrationError)):
                    raise exc
                if attempt == self.max_retries:
                    raise exc
            except Exception as exc:
                last_error = IntegrationNetworkError(self.provider.value, str(exc))
                if attempt == self.max_retries:
                    raise last_error from exc

            # Exponential backoff delay before next retry
            backoff_delay = self.backoff_base * (2 ** (attempt - 1))
            await asyncio.sleep(backoff_delay)

        if last_error is not None:
            raise last_error
        raise IntegrationError(self.provider.value, f"Operation '{operation_name}' failed after {self.max_retries} attempts")
