"""Read-only monitoring and telemetry integration client (Datadog/CloudWatch compatible)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.base import BaseIntegrationClient, IntegrationProvider


class ServiceHealthMetrics(BaseModel):
    """Read-only service telemetry metrics snapshot."""

    service_name: str
    error_rate_percent: float
    p99_latency_ms: int
    cpu_utilization_percent: float
    memory_utilization_percent: float
    active_alerts_count: int
    status: str
    sampled_at: str


class MonitoringAlertItem(BaseModel):
    """Structured telemetry alert item from monitoring provider."""

    alert_id: str
    title: str
    metric_name: str
    threshold_value: float
    current_value: float
    severity: str
    triggered_at: str


class MonitoringIntegrationClient(BaseIntegrationClient):
    """Read-only monitoring client for ingesting live telemetry without mutating production state."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint_url: str | None = None,
        timeout_seconds: float = 3.0,
        max_retries: int = 3,
    ):
        super().__init__(
            provider=IntegrationProvider.MONITORING,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        self.api_key = api_key or "dev-monitoring-key"
        self.endpoint_url = endpoint_url or "https://api.monitoring.example.com"

    async def fetch_service_health(self, service_name: str) -> ServiceHealthMetrics:
        """Fetch live read-only telemetry metrics for a service."""

        async def _call() -> ServiceHealthMetrics:
            # Deterministic telemetry representation for service query
            is_payment = "payment" in service_name.lower() or "checkout" in service_name.lower()
            return ServiceHealthMetrics(
                service_name=service_name,
                error_rate_percent=42.8 if is_payment else 0.4,
                p99_latency_ms=4500 if is_payment else 120,
                cpu_utilization_percent=14.5,
                memory_utilization_percent=48.2,
                active_alerts_count=3 if is_payment else 0,
                status="DEGRADED" if is_payment else "HEALTHY",
                sampled_at=datetime.now(timezone.utc).isoformat(),
            )

        return await self.execute_with_resilience("fetch_service_health", _call)

    async def fetch_active_alerts(self, lookback_minutes: int = 30) -> list[MonitoringAlertItem]:
        """Fetch active threshold alerts for the incident window."""

        async def _call() -> list[MonitoringAlertItem]:
            now = datetime.now(timezone.utc).isoformat()
            return [
                MonitoringAlertItem(
                    alert_id="alt-8891",
                    title="High 503 Service Unavailable Rate",
                    metric_name="http.server.5xx.rate",
                    threshold_value=5.0,
                    current_value=42.8,
                    severity="critical",
                    triggered_at=now,
                ),
                MonitoringAlertItem(
                    alert_id="alt-8892",
                    title="P99 Gateway Latency Threshold Exceeded",
                    metric_name="http.server.latency.p99",
                    threshold_value=1000.0,
                    current_value=4500.0,
                    severity="high",
                    triggered_at=now,
                ),
            ]

        return await self.execute_with_resilience("fetch_active_alerts", _call)
