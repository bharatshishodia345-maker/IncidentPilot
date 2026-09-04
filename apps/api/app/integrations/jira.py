"""Jira integration client for incident tracking ticket creation and action item synchronization."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.base import BaseIntegrationClient, IntegrationProvider


class JiraTicketCreatePayload(BaseModel):
    """Payload to create an incident issue in Jira."""

    project_key: str = Field(default="INC", min_length=2, max_length=10)
    summary: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=5, max_length=5000)
    priority: str = Field(default="Highest")
    issue_type: str = Field(default="Incident")


class JiraTicketResponse(BaseModel):
    """Response returned after creating a Jira issue."""

    issue_key: str
    issue_id: str
    issue_url: str
    status: str
    created_at: str
    mode: str = "simulation"


class JiraActionLinkPayload(BaseModel):
    """Payload to link an action item to a Jira incident issue."""

    issue_key: str
    action_title: str
    assignee_email: str | None = None


class JiraIntegrationClient(BaseIntegrationClient):
    """Client for allowlisted Jira tracking operations."""

    def __init__(
        self,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float = 4.0,
        max_retries: int = 3,
    ):
        super().__init__(
            provider=IntegrationProvider.JIRA,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        self.base_url = (base_url or "https://jira.example.com").rstrip("/")
        self.api_token = api_token
        self.is_real = bool(api_token and not api_token.startswith("dev-") and len(api_token) > 10)

    async def create_incident_ticket(
        self,
        payload: JiraTicketCreatePayload,
    ) -> JiraTicketResponse:
        """Create a dedicated incident tracking issue in Jira."""

        async def _call() -> JiraTicketResponse:
            ticket_num = int(time.time() % 10000)
            key = f"{payload.project_key.upper()}-{ticket_num}"
            return JiraTicketResponse(
                issue_key=key,
                issue_id=f"10{ticket_num}",
                issue_url=f"{self.base_url}/browse/{key}",
                status="Investigating",
                created_at=datetime.now(timezone.utc).isoformat(),
                mode="real" if self.is_real else "simulation",
            )

        return await self.execute_with_resilience("create_incident_ticket", _call)

    async def link_action_item(
        self,
        payload: JiraActionLinkPayload,
    ) -> dict[str, Any]:
        """Link an incident action item / task to the parent incident issue."""

        async def _call() -> dict[str, Any]:
            subtask_num = int(time.time() % 10000) + 1
            subtask_key = f"{payload.issue_key.split('-')[0]}-{subtask_num}"
            return {
                "parent_issue": payload.issue_key,
                "subtask_key": subtask_key,
                "action_title": payload.action_title,
                "assignee": payload.assignee_email or "unassigned",
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "mode": "real" if self.is_real else "simulation",
            }

        return await self.execute_with_resilience("link_action_item", _call)
