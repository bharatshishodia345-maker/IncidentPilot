"""Standards-compliant Agora AccessToken2, RTC/RTM Token builder, and Conversational AI REST Client."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time
import uuid
import zlib
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def pack_uint16(val: int) -> bytes:
    return struct.pack("<H", int(val))


def unpack_uint16(buf: bytes) -> tuple[int, bytes]:
    size = struct.calcsize("H")
    return struct.unpack("<H", buf[:size])[0], buf[size:]


def pack_uint32(val: int) -> bytes:
    return struct.pack("<I", int(val))


def unpack_uint32(buf: bytes) -> tuple[int, bytes]:
    size = struct.calcsize("I")
    return struct.unpack("<I", buf[:size])[0], buf[size:]


def pack_string(val: str | bytes) -> bytes:
    data = val.encode("utf-8") if isinstance(val, str) else val
    return pack_uint16(len(data)) + data


def unpack_string(buf: bytes) -> tuple[str, bytes]:
    length, rest = unpack_uint16(buf)
    return rest[:length].decode("utf-8", errors="replace"), rest[length:]


def pack_map_uint32(mapping: dict[int, int]) -> bytes:
    res = pack_uint16(len(mapping))
    for k, v in sorted(mapping.items()):
        res += pack_uint16(k) + pack_uint32(v)
    return res


class RtcPrivilege:
    JOIN_CHANNEL = 1
    PUBLISH_AUDIO_STREAM = 2
    PUBLISH_VIDEO_STREAM = 3
    PUBLISH_DATA_STREAM = 4


class RtmPrivilege:
    LOGIN = 1


class ServiceRtc:
    """Service representing Agora Real-Time Communication permissions."""

    SERVICE_TYPE = 1

    def __init__(self, channel_name: str, uid: int | str = 0) -> None:
        self.channel_name = channel_name
        self.uid = str(uid) if uid != 0 else ""
        self.privileges: dict[int, int] = {}

    def add_privilege(self, privilege: int, expire_ts: int) -> None:
        self.privileges[privilege] = expire_ts

    def pack(self) -> bytes:
        header = pack_uint16(self.SERVICE_TYPE) + pack_map_uint32(self.privileges)
        return header + pack_string(self.channel_name) + pack_string(self.uid)


class ServiceRtm:
    """Service representing Agora Real-Time Messaging permissions."""

    SERVICE_TYPE = 2

    def __init__(self, user_id: str) -> None:
        self.user_id = str(user_id)
        self.privileges: dict[int, int] = {}

    def add_privilege(self, privilege: int, expire_ts: int) -> None:
        self.privileges[privilege] = expire_ts

    def pack(self) -> bytes:
        header = pack_uint16(self.SERVICE_TYPE) + pack_map_uint32(self.privileges)
        return header + pack_string(self.user_id)


class AccessToken2:
    """Agora AccessToken2 specification builder."""

    VERSION = "007"

    def __init__(
        self,
        app_id: str,
        app_certificate: str,
        issue_ts: int | None = None,
        expire_seconds: int = 3600,
    ) -> None:
        self.app_id = app_id
        self.app_certificate = app_certificate
        self.issue_ts = issue_ts or int(time.time())
        self.expire = expire_seconds
        self.salt = secrets.randbits(32)
        self.services: list[ServiceRtc | ServiceRtm] = []

    def add_service(self, service: ServiceRtc | ServiceRtm) -> None:
        self.services.append(service)

    def build(self) -> str:
        # 1. Generate signing key: HMAC-SHA256(issue_ts, app_certificate)
        issue_ts_bytes = pack_uint32(self.issue_ts)
        signing_key = hmac.new(
            self.app_certificate.encode("utf-8"),
            issue_ts_bytes,
            hashlib.sha256,
        ).digest()

        # 2. Serialize services
        services_data = pack_uint16(len(self.services))
        for service in self.services:
            services_data += service.pack()

        # 3. Assemble message payload
        message = (
            pack_string(self.app_id)
            + pack_uint32(self.issue_ts)
            + pack_uint32(self.expire)
            + pack_uint32(self.salt)
            + services_data
        )

        # 4. Generate signature
        signature = hmac.new(signing_key, message, hashlib.sha256).digest()

        # 5. Combine and compress
        content = signature + message
        compressed = zlib.compress(content)

        # 6. Return Version + Base64
        return f"{self.VERSION}{base64.b64encode(compressed).decode('utf-8')}"


class AgoraTokenService:
    """High-level generator for IncidentPilot Agora RTC & RTM room tokens."""

    @staticmethod
    def generate_rtc_token(
        app_id: str,
        app_certificate: str,
        channel_name: str,
        uid: int | str,
        is_publisher: bool = True,
        expire_seconds: int = 3600,
    ) -> str:
        """Generate a secure AccessToken2 for an incident voice channel."""
        now = int(time.time())
        token_builder = AccessToken2(
            app_id=app_id,
            app_certificate=app_certificate,
            issue_ts=now,
            expire_seconds=expire_seconds,
        )

        rtc_service = ServiceRtc(channel_name=channel_name, uid=uid)
        rtc_service.add_privilege(RtcPrivilege.JOIN_CHANNEL, expire_seconds)
        if is_publisher:
            rtc_service.add_privilege(RtcPrivilege.PUBLISH_AUDIO_STREAM, expire_seconds)
            rtc_service.add_privilege(RtcPrivilege.PUBLISH_DATA_STREAM, expire_seconds)

        token_builder.add_service(rtc_service)
        return token_builder.build()

    @staticmethod
    def generate_rtm_token(
        app_id: str,
        app_certificate: str,
        user_id: str,
        expire_seconds: int = 3600,
    ) -> str:
        """Generate a secure AccessToken2 for RTM signaling and transcripts."""
        now = int(time.time())
        token_builder = AccessToken2(
            app_id=app_id,
            app_certificate=app_certificate,
            issue_ts=now,
            expire_seconds=expire_seconds,
        )
        rtm_service = ServiceRtm(user_id=user_id)
        rtm_service.add_privilege(RtmPrivilege.LOGIN, expire_seconds)
        token_builder.add_service(rtm_service)
        return token_builder.build()

    @staticmethod
    def generate_combined_token(
        app_id: str,
        app_certificate: str,
        channel_name: str,
        uid: int | str,
        is_publisher: bool = True,
        expire_seconds: int = 3600,
    ) -> str:
        """Generate a combined RTC + RTM token for ConvoAI Agent / Server Auth."""
        now = int(time.time())
        token_builder = AccessToken2(
            app_id=app_id,
            app_certificate=app_certificate,
            issue_ts=now,
            expire_seconds=expire_seconds,
        )

        rtc_service = ServiceRtc(channel_name=channel_name, uid=uid)
        rtc_service.add_privilege(RtcPrivilege.JOIN_CHANNEL, expire_seconds)
        if is_publisher:
            rtc_service.add_privilege(RtcPrivilege.PUBLISH_AUDIO_STREAM, expire_seconds)
            rtc_service.add_privilege(RtcPrivilege.PUBLISH_DATA_STREAM, expire_seconds)
        token_builder.add_service(rtc_service)

        rtm_service = ServiceRtm(user_id=str(uid))
        rtm_service.add_privilege(RtmPrivilege.LOGIN, expire_seconds)
        token_builder.add_service(rtm_service)

        return token_builder.build()


class ConvoAIAgentStatus(str, Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SIMULATED_RUNNING = "SIMULATED_RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class AgoraAgentSession:
    """Represents an active or historic ConvoAI agent session for an incident room."""

    def __init__(
        self,
        incident_id: str,
        channel_name: str,
        agent_id: str,
        status: ConvoAIAgentStatus,
        mode: str,
        agent_rtc_uid: str = "999",
        error_message: str | None = None,
    ) -> None:
        self.incident_id = incident_id
        self.channel_name = channel_name
        self.agent_id = agent_id
        self.status = status
        self.mode = mode
        self.agent_rtc_uid = agent_rtc_uid
        self.error_message = error_message
        self.created_at = int(time.time())
        self.updated_at = int(time.time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "channel": self.channel_name,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "mode": self.mode,
            "agent_rtc_uid": self.agent_rtc_uid,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AgoraAgentSessionManager:
    """Manages active Conversational AI agent sessions per incident room to prevent duplicates."""

    _sessions: dict[str, AgoraAgentSession] = {}

    @classmethod
    def get_session(cls, channel_name: str) -> AgoraAgentSession | None:
        return cls._sessions.get(channel_name)

    @classmethod
    def register_session(cls, session: AgoraAgentSession) -> None:
        cls._sessions[session.channel_name] = session

    @classmethod
    def update_status(
        cls,
        channel_name: str,
        status: ConvoAIAgentStatus,
        error_message: str | None = None,
    ) -> AgoraAgentSession | None:
        sess = cls._sessions.get(channel_name)
        if sess:
            sess.status = status
            sess.error_message = error_message
            sess.updated_at = int(time.time())
        return sess

    @classmethod
    def remove_session(cls, channel_name: str) -> None:
        cls._sessions.pop(channel_name, None)


class AgoraConvoAIService:
    """Official Agora Conversational AI Agent lifecycle manager (REST API v2)."""

    BASE_URL = "https://api.agora.io/api/conversational-ai-agent/v2/projects"

    def __init__(
        self,
        app_id: str,
        app_certificate: str,
        stt_vendor: str = "deepgram",
        llm_vendor: str = "openai",
        tts_vendor: str = "minimax",
    ) -> None:
        self.app_id = app_id
        self.app_certificate = app_certificate
        self.stt_vendor = stt_vendor
        self.llm_vendor = llm_vendor
        self.tts_vendor = tts_vendor

    def is_live_credentials(self) -> bool:
        """Verify whether real live Agora credentials are configured."""
        if not self.app_id or not self.app_certificate:
            return False
        if "dev-" in self.app_id or "test_" in self.app_id or "000000" in self.app_certificate:
            return False
        return True

    async def start_agent(
        self,
        channel_name: str,
        incident_id: str | None = None,
        agent_name: str | None = None,
        instructions: str | None = None,
        greeting: str | None = None,
        language: str = "en-US",
    ) -> dict[str, Any]:
        """Start an Agora Conversational AI agent to join the RTC war room channel.

        Maintains one active agent per incident room.
        """
        # 1. Check for existing active session
        existing = AgoraAgentSessionManager.get_session(channel_name)
        if existing and existing.status in (ConvoAIAgentStatus.RUNNING, ConvoAIAgentStatus.SIMULATED_RUNNING, ConvoAIAgentStatus.STARTING):
            logger.info("Reusing existing active ConvoAI session for channel %s: %s", channel_name, existing.agent_id)
            return existing.to_dict()

        inc_id = incident_id or channel_name.replace("incident-", "")
        agent_uid = "999"
        unique_name = agent_name or f"incidentpilot_{uuid.uuid4().hex[:8]}"

        agent_token = AgoraTokenService.generate_combined_token(
            app_id=self.app_id,
            app_certificate=self.app_certificate,
            channel_name=channel_name,
            uid=agent_uid,
            is_publisher=True,
        )

        default_prompt = (
            "You are IncidentPilot, an AI incident co-commander. "
            "Listen carefully, extract facts and hypotheses, ask useful clarifying questions, "
            "recommend safe actions with human authorization, and maintain calm situational awareness."
        )

        payload: dict[str, Any] = {
            "name": unique_name,
            "properties": {
                "channel": channel_name,
                "token": agent_token,
                "agent_rtc_uid": agent_uid,
                "remote_rtc_uids": ["*"],
                "enable_string_uid": False,
                "idle_timeout": 300,
                "asr": {
                    "vendor": self.stt_vendor,
                    "language": language,
                },
                "llm": {
                    "vendor": self.llm_vendor,
                    "model": "gpt-4o-mini",
                    "system_messages": [{"role": "system", "content": instructions or default_prompt}],
                    "greeting_message": greeting or "IncidentPilot Co-Commander online and listening.",
                },
                "tts": {
                    "vendor": self.tts_vendor,
                    "params": {"voice_id": "male-qn-qingse"},
                },
            },
            "advanced_features": {
                "enable_rtm": True,
            },
            "parameters": {
                "data_channel": "rtm",
                "enable_metrics": True,
                "enable_error_message": True,
            },
        }

        # 2. Live production credentials path
        if self.is_live_credentials():
            server_token = AgoraTokenService.generate_combined_token(
                app_id=self.app_id,
                app_certificate=self.app_certificate,
                channel_name=channel_name,
                uid="convoai-server",
                is_publisher=True,
            )
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"agora token={server_token}",
            }
            url = f"{self.BASE_URL}/{self.app_id}/join"
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code in (200, 201):
                        resp_data = resp.json()
                        agent_id = resp_data.get("agent_id") or resp_data.get("id") or f"agora-agent-{uuid.uuid4().hex[:8]}"
                        session = AgoraAgentSession(
                            incident_id=inc_id,
                            channel_name=channel_name,
                            agent_id=agent_id,
                            status=ConvoAIAgentStatus.RUNNING,
                            mode="agora_live",
                            agent_rtc_uid=agent_uid,
                        )
                        AgoraAgentSessionManager.register_session(session)
                        return session.to_dict()
                    else:
                        error_msg = f"Agora ConvoAI API returned {resp.status_code}: {resp.text}"
                        logger.error(error_msg)
                        session = AgoraAgentSession(
                            incident_id=inc_id,
                            channel_name=channel_name,
                            agent_id="failed",
                            status=ConvoAIAgentStatus.FAILED,
                            mode="agora_live",
                            agent_rtc_uid=agent_uid,
                            error_message=error_msg,
                        )
                        AgoraAgentSessionManager.register_session(session)
                        return session.to_dict()
                except Exception as ex:
                    error_msg = f"Error connecting to Agora ConvoAI REST API: {ex}"
                    logger.error(error_msg)
                    session = AgoraAgentSession(
                        incident_id=inc_id,
                        channel_name=channel_name,
                        agent_id="failed",
                        status=ConvoAIAgentStatus.FAILED,
                        mode="agora_live",
                        agent_rtc_uid=agent_uid,
                        error_message=error_msg,
                    )
                    AgoraAgentSessionManager.register_session(session)
                    return session.to_dict()

        # 3. Explicit development simulation path (never masked as real live agent)
        simulated_agent_id = f"sim-convoai-{uuid.uuid4().hex[:8]}"
        session = AgoraAgentSession(
            incident_id=inc_id,
            channel_name=channel_name,
            agent_id=simulated_agent_id,
            status=ConvoAIAgentStatus.SIMULATED_RUNNING,
            mode="development_simulation",
            agent_rtc_uid=agent_uid,
        )
        AgoraAgentSessionManager.register_session(session)
        logger.info(
            "ConvoAI Agent initialized in room %s (agent_id: %s, mode: development_simulation)",
            channel_name,
            simulated_agent_id,
        )
        return session.to_dict()

    async def stop_agent(self, channel_name: str, agent_id: str | None = None) -> dict[str, Any]:
        """Stop an active ConvoAI agent and clean up room session."""
        session = AgoraAgentSessionManager.get_session(channel_name)
        target_agent_id = agent_id or (session.agent_id if session else None)

        if not target_agent_id or target_agent_id == "failed":
            AgoraAgentSessionManager.remove_session(channel_name)
            return {"status": "STOPPED", "channel": channel_name}

        if self.is_live_credentials() and not target_agent_id.startswith("sim-convoai-"):
            server_token = AgoraTokenService.generate_combined_token(
                app_id=self.app_id,
                app_certificate=self.app_certificate,
                channel_name=channel_name,
                uid="convoai-server",
                is_publisher=True,
            )
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"agora token={server_token}",
            }
            url = f"{self.BASE_URL}/{self.app_id}/agents/{target_agent_id}/leave"
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    resp = await client.post(url, headers=headers)
                    if resp.status_code == 200:
                        AgoraAgentSessionManager.update_status(channel_name, ConvoAIAgentStatus.STOPPED)
                        return {"status": "STOPPED", "channel": channel_name, "agent_id": target_agent_id}
                except Exception as ex:
                    logger.warning("Error stopping ConvoAI agent: %s", ex)

        AgoraAgentSessionManager.update_status(channel_name, ConvoAIAgentStatus.STOPPED)
        return {"status": "STOPPED", "channel": channel_name, "agent_id": target_agent_id}

    @staticmethod
    def get_agent_status(channel_name: str) -> dict[str, Any]:
        """Return the current agent session status for an incident room."""
        session = AgoraAgentSessionManager.get_session(channel_name)
        if session:
            return session.to_dict()
        return {
            "channel": channel_name,
            "status": ConvoAIAgentStatus.STOPPED.value,
            "mode": "none",
            "agent_id": None,
        }
