"""Incident live room and Agora RTC / Conversational AI voice coordination endpoints."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AgentStatusResponse,
    AgoraTokenResponse,
    ParticipantPresence,
    RoomJoinResponse,
    RoomLeaveResponse,
)
from app.auth.dependencies import Principal, get_current_principal
from app.config import Settings, get_settings
from app.core.exceptions import EntityNotFoundError
from app.db.models import User, UserRole
from app.db.session import get_db
from app.services.agora import AgoraAgentSessionManager, AgoraConvoAIService, AgoraTokenService
from app.services.incident_service import IncidentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["room"])


def _resolve_user(session: Session, principal: Principal) -> User:
    """Resolve the active DB User instance for the principal."""
    if principal.user_id is not None:
        user = session.scalar(
            select(User).where(User.id == principal.user_id, User.organization_id == principal.organization_id)
        )
        if user is not None:
            return user

    user = session.scalar(
        select(User).where(User.subject == principal.subject, User.organization_id == principal.organization_id)
    )
    if user is None:
        raise EntityNotFoundError("User", f"subject={principal.subject}")
    return user


def _build_agora_tokens(
    settings: Settings,
    channel_name: str,
    uid: str,
    is_publisher: bool,
) -> tuple[str, str, str]:
    """Generate tokens using configured Agora secrets or fallback development key."""
    app_id = settings.agora_app_id or "dev-incidentpilot-agora-app-id"
    app_cert = settings.agora_app_certificate.get_secret_value() if settings.agora_app_certificate else "dev-cert-0000000000000000000000"

    rtc_token = AgoraTokenService.generate_rtc_token(
        app_id=app_id,
        app_certificate=app_cert,
        channel_name=channel_name,
        uid=uid,
        is_publisher=is_publisher,
        expire_seconds=settings.agora_token_expire_seconds,
    )
    rtm_token = AgoraTokenService.generate_rtm_token(
        app_id=app_id,
        app_certificate=app_cert,
        user_id=uid,
        expire_seconds=settings.agora_token_expire_seconds,
    )
    return app_id, rtc_token, rtm_token


@router.post("/incidents/{incident_id}/room/join", response_model=RoomJoinResponse)
async def join_incident_room(
    incident_id: UUID,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> RoomJoinResponse:
    """Join the incident live voice room, update presence, start/reuse Agora ConvoAI co-commander, and generate tokens."""
    user = _resolve_user(session, principal)
    settings: Settings = getattr(request.app.state, "settings", get_settings())

    # 1. Update presence state in DB
    IncidentService.join_room(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        user_id=user.id,
    )

    # 2. Channel & permissions
    channel_name = f"incident-{incident_id}"
    uid = str(user.id)
    is_publisher = user.role in {UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER}

    # 3. Generate tokens
    app_id, rtc_token, rtm_token = _build_agora_tokens(
        settings=settings,
        channel_name=channel_name,
        uid=uid,
        is_publisher=is_publisher,
    )

    # 4. Start/Attach Agora Conversational AI Agent for the war room (prevents duplicate sessions)
    app_cert = settings.agora_app_certificate.get_secret_value() if settings.agora_app_certificate else "dev-cert-0000000000000000000000"
    convoai_service = AgoraConvoAIService(
        app_id=app_id,
        app_certificate=app_cert,
        stt_vendor="deepgram",
        llm_vendor="openai",
        tts_vendor="minimax",
    )
    agent_info = await convoai_service.start_agent(
        channel_name=channel_name,
        incident_id=str(incident_id),
        agent_name=f"cocommander_{str(incident_id)[:8]}",
        instructions=(
            "You are IncidentPilot, an AI co-commander for technical incident management. "
            "Maintain evidence-first discipline: separate verified facts from speculative hypotheses. "
            "Never invent a root cause. Ask one clear diagnostic question per turn. "
            "Recommend safe remediations requiring human authorization."
        ),
        greeting="IncidentPilot Co-Commander connected. Please state the incident symptoms.",
    )
    agent_id = agent_info.get("agent_id")
    agent_status = agent_info.get("status", "RUNNING")
    agent_mode = agent_info.get("mode", "development_simulation")

    # 5. Fetch all participants for room roster
    presence_rows = IncidentService.get_room_presence(session, principal.organization_id, incident_id)
    participants = [
        ParticipantPresence(
            user_id=p.user_id,
            display_name=u.display_name,
            email=u.email,
            role=u.role,
            presence_state=p.presence_state,
            joined_at=p.joined_at,
            left_at=p.left_at,
        )
        for p, u in presence_rows
    ]

    return RoomJoinResponse(
        app_id=app_id,
        channel_name=channel_name,
        token=rtc_token,
        rtm_token=rtm_token,
        agent_id=agent_id,
        agent_status=agent_status,
        agent_mode=agent_mode,
        uid=uid,
        role=user.role,
        is_publisher=is_publisher,
        expires_in_seconds=settings.agora_token_expire_seconds,
        participants=participants,
    )


@router.post("/incidents/{incident_id}/room/leave", response_model=RoomLeaveResponse)
async def leave_incident_room(
    incident_id: UUID,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> RoomLeaveResponse:
    """Leave the incident voice room, update presence, and clean up agent session if empty."""
    user = _resolve_user(session, principal)

    IncidentService.leave_room(
        session=session,
        organization_id=principal.organization_id,
        incident_id=incident_id,
        user_id=user.id,
    )

    # Check remaining active participants in room
    channel_name = f"incident-{incident_id}"
    presence_rows = IncidentService.get_room_presence(session, principal.organization_id, incident_id)
    active_publishers = [
        p for p, u in presence_rows
        if p.presence_state.value == "joined" and u.role in {UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER}
    ]

    # If no responders or commanders remain in the room, stop the ConvoAI agent
    if not active_publishers:
        settings: Settings = getattr(request.app.state, "settings", get_settings())
        app_id = settings.agora_app_id or "dev-incidentpilot-agora-app-id"
        app_cert = settings.agora_app_certificate.get_secret_value() if settings.agora_app_certificate else "dev-cert-0000000000000000000000"
        convoai_service = AgoraConvoAIService(app_id=app_id, app_certificate=app_cert)
        await convoai_service.stop_agent(channel_name=channel_name)

    return RoomLeaveResponse(
        incident_id=incident_id,
        user_id=user.id,
        status="left",
    )


@router.get("/incidents/{incident_id}/room/presence", response_model=list[ParticipantPresence])
def get_room_presence(
    incident_id: UUID,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> list[ParticipantPresence]:
    """List real-time presence states of all participants in the incident voice room."""
    presence_rows = IncidentService.get_room_presence(session, principal.organization_id, incident_id)
    return [
        ParticipantPresence(
            user_id=p.user_id,
            display_name=u.display_name,
            email=u.email,
            role=u.role,
            presence_state=p.presence_state,
            joined_at=p.joined_at,
            left_at=p.left_at,
        )
        for p, u in presence_rows
    ]


@router.get("/incidents/{incident_id}/room/agent/status", response_model=AgentStatusResponse)
def get_incident_agent_status(
    incident_id: UUID,
    principal: Principal = Depends(get_current_principal),
) -> AgentStatusResponse:
    """Query the active Agora Conversational AI agent status for this incident war room."""
    channel_name = f"incident-{incident_id}"
    status_info = AgoraConvoAIService.get_agent_status(channel_name)
    return AgentStatusResponse(
        channel=status_info.get("channel", channel_name),
        agent_id=status_info.get("agent_id"),
        status=status_info.get("status", "STOPPED"),
        mode=status_info.get("mode", "none"),
        agent_rtc_uid=status_info.get("agent_rtc_uid", "999"),
        error_message=status_info.get("error_message"),
    )


@router.post("/incidents/{incident_id}/room/agent/stop", response_model=AgentStatusResponse)
async def stop_incident_agent(
    incident_id: UUID,
    request: Request,
    principal: Principal = Depends(get_current_principal),
) -> AgentStatusResponse:
    """Manually stop the active Agora Conversational AI agent session for this incident."""
    channel_name = f"incident-{incident_id}"
    settings: Settings = getattr(request.app.state, "settings", get_settings())
    app_id = settings.agora_app_id or "dev-incidentpilot-agora-app-id"
    app_cert = settings.agora_app_certificate.get_secret_value() if settings.agora_app_certificate else "dev-cert-0000000000000000000000"

    convoai_service = AgoraConvoAIService(app_id=app_id, app_certificate=app_cert)
    result = await convoai_service.stop_agent(channel_name=channel_name)
    return AgentStatusResponse(
        channel=channel_name,
        agent_id=result.get("agent_id"),
        status=result.get("status", "STOPPED"),
        mode="stopped",
        agent_rtc_uid="999",
    )


@router.post("/incidents/{incident_id}/agora-token", response_model=AgoraTokenResponse)
def refresh_agora_token(
    incident_id: UUID,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> AgoraTokenResponse:
    """Generate or refresh an Agora RTC and RTM token for the incident voice channel."""
    user = _resolve_user(session, principal)
    settings: Settings = getattr(request.app.state, "settings", get_settings())

    IncidentService.get_incident(session, principal.organization_id, incident_id)

    channel_name = f"incident-{incident_id}"
    uid = str(user.id)
    is_publisher = user.role in {UserRole.INCIDENT_COMMANDER, UserRole.RESPONDER}

    app_id, rtc_token, rtm_token = _build_agora_tokens(
        settings=settings,
        channel_name=channel_name,
        uid=uid,
        is_publisher=is_publisher,
    )

    agent_status_info = AgoraConvoAIService.get_agent_status(channel_name)
    agent_id = agent_status_info.get("agent_id")

    return AgoraTokenResponse(
        app_id=app_id,
        channel_name=channel_name,
        token=rtc_token,
        rtm_token=rtm_token,
        agent_id=agent_id,
        uid=uid,
        expires_in_seconds=settings.agora_token_expire_seconds,
    )
