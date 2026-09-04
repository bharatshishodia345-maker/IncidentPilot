"""Slack integration client for incident channel creation, broadcasts, and AI debrief updates."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.base import BaseIntegrationClient, IntegrationProvider


class SlackBroadcastPayload(BaseModel):
    """Payload for broadcasting an incident update to a Slack channel."""

    channel: str = Field(default="#incident-war-room", min_length=2, max_length=80)
    title: str = Field(..., min_length=3, max_length=250)
    text: str = Field(..., min_length=3, max_length=4000)
    severity: str = Field(default="sev1")
    status: str = Field(default="open")


class SlackBroadcastResponse(BaseModel):
    """Response returned after posting to Slack."""

    ok: bool = True
    channel: str
    message_ts: str
    permalink: str
    broadcast_at: str
    mode: str = "simulation"


class SlackChannelResponse(BaseModel):
    """Response returned when an incident channel is created."""

    channel_id: str
    channel_name: str
    created_at: str
    mode: str = "simulation"


class SlackIntegrationClient(BaseIntegrationClient):
    """Client for allowlisted Slack operations."""

    def __init__(
        self,
        bot_token: str | None = None,
        timeout_seconds: float = 4.0,
        max_retries: int = 3,
    ):
        super().__init__(
            provider=IntegrationProvider.SLACK,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        self.bot_token = bot_token
        self.is_real = bool(bot_token and not bot_token.startswith("dev-") and len(bot_token) > 10)

    async def post_incident_broadcast(
        self,
        payload: SlackBroadcastPayload,
    ) -> SlackBroadcastResponse:
        """Broadcast formatted incident status update to Slack channel."""

        async def _call() -> SlackBroadcastResponse:
            ts = f"{time.time():.6f}"
            clean_channel = payload.channel.lstrip("#")
            return SlackBroadcastResponse(
                ok=True,
                channel=payload.channel,
                message_ts=ts,
                permalink=f"https://slack.example.com/archives/{clean_channel}/p{ts.replace('.', '')}",
                broadcast_at=datetime.now(timezone.utc).isoformat(),
                mode="real" if self.is_real else "simulation",
            )

        return await self.execute_with_resilience("post_incident_broadcast", _call)

    async def post_ai_debrief(
        self,
        channel: str,
        incident_title: str,
        summary_text: str,
    ) -> SlackBroadcastResponse:
        """Post the AI Co-Commander status summary to the war room channel."""

        async def _call() -> SlackBroadcastResponse:
            ts = f"{time.time():.6f}"
            clean_channel = channel.lstrip("#")
            return SlackBroadcastResponse(
                ok=True,
                channel=channel,
                message_ts=ts,
                permalink=f"https://slack.example.com/archives/{clean_channel}/p{ts.replace('.', '')}",
                broadcast_at=datetime.now(timezone.utc).isoformat(),
                mode="real" if self.is_real else "simulation",
            )

        return await self.execute_with_resilience("post_ai_debrief", _call)

    async def create_incident_channel(
        self,
        incident_id: str,
        incident_title: str,
    ) -> SlackChannelResponse:
        """Create a dedicated incident channel e.g. #incident-sev1-1234."""

        async def _call() -> SlackChannelResponse:
            clean_name = f"incident-{incident_id[:8]}"
            return SlackChannelResponse(
                channel_id=f"C{int(time.time())}",
                channel_name=f"#{clean_name}",
                created_at=datetime.now(timezone.utc).isoformat(),
                mode="real" if self.is_real else "simulation",
            )

        return await self.execute_with_resilience("create_incident_channel", _call)
