"""Allowlisted action parameter schemas, risk levels, and validation models."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def default_utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AllowlistedActionType(str, Enum):
    """Strictly allowlisted action types permitted in IncidentPilot."""

    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    RESTART_SERVICE = "restart_service"
    DRAIN_TRAFFIC = "drain_traffic"
    SCALE_REPLICAS = "scale_replicas"
    ENABLE_RATE_LIMITING = "enable_rate_limiting"
    FLUSH_CACHE = "flush_cache"
    BLOCK_IP = "block_ip"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProposalStatus(str, Enum):
    NONE = "none"
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    EXECUTED = "executed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


# Parameter name safety regex: alphanumeric, dash, underscore only (prevents command/script injection)
SAFE_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9\-_]{2,64}$")
SAFE_VERSION_REGEX = re.compile(r"^[a-zA-Z0-9\.\-_]{1,64}$")
SAFE_ENDPOINT_REGEX = re.compile(r"^\/[a-zA-Z0-9\-_/\{\}\*\.\:\?]*$")
SAFE_IP_REGEX = re.compile(r"^([0-9]{1,3}\.){3}[0-9]{1,3}(\/[0-9]{1,2})?$")


class RollbackDeploymentParams(BaseModel):
    service_name: str = Field(..., description="Target service to roll back")
    target_version: str = Field(..., description="Previous stable deployment version/tag")
    cluster: str = Field(default="production-primary", description="Target cluster environment")

    @field_validator("service_name", "cluster")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        trimmed = value.strip()
        if not SAFE_IDENTIFIER_REGEX.match(trimmed):
            raise ValueError(f"Identifier '{value}' contains invalid characters or length")
        return trimmed

    @field_validator("target_version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        trimmed = value.strip()
        if not SAFE_VERSION_REGEX.match(trimmed):
            raise ValueError(f"Version '{value}' contains invalid characters")
        return trimmed


class RestartServiceParams(BaseModel):
    service_name: str = Field(..., description="Target service to restart")
    grace_period_seconds: int = Field(default=30, ge=0, le=300, description="Grace period before pod termination")

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not SAFE_IDENTIFIER_REGEX.match(trimmed):
            raise ValueError(f"Service name '{value}' contains invalid characters")
        return trimmed


class DrainTrafficParams(BaseModel):
    service_name: str = Field(..., description="Target service to drain")
    drain_percentage: int = Field(..., ge=1, le=100, description="Percentage of traffic to reroute")
    region: str = Field(default="eu-central-1", description="Geographic or cloud region")

    @field_validator("service_name", "region")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        trimmed = value.strip()
        if not SAFE_IDENTIFIER_REGEX.match(trimmed):
            raise ValueError(f"Value '{value}' contains invalid characters")
        return trimmed


class ScaleReplicasParams(BaseModel):
    service_name: str = Field(..., description="Target service deployment to scale")
    replica_count: int = Field(..., ge=1, le=50, description="Target replica count")

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not SAFE_IDENTIFIER_REGEX.match(trimmed):
            raise ValueError(f"Service name '{value}' contains invalid characters")
        return trimmed


class EnableRateLimitingParams(BaseModel):
    endpoint_pattern: str = Field(..., description="URL endpoint pattern to rate limit")
    rate_limit_rpm: int = Field(..., ge=10, le=100000, description="Requests per minute limit")

    @field_validator("endpoint_pattern")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        trimmed = value.strip()
        if not SAFE_ENDPOINT_REGEX.match(trimmed):
            raise ValueError(f"Endpoint pattern '{value}' contains invalid characters")
        return trimmed


class FlushCacheParams(BaseModel):
    cache_cluster: str = Field(..., description="Cache cluster identifier (e.g. redis-primary)")
    key_pattern: str = Field(default="*", description="Key pattern to evict")

    @field_validator("cache_cluster")
    @classmethod
    def validate_cluster(cls, value: str) -> str:
        trimmed = value.strip()
        if not SAFE_IDENTIFIER_REGEX.match(trimmed):
            raise ValueError(f"Cache cluster '{value}' contains invalid characters")
        return trimmed


class BlockIpParams(BaseModel):
    ip_address: str = Field(..., description="IP address or CIDR range to block (e.g. 198.51.100.4)")
    duration_minutes: int = Field(default=60, ge=1, le=1440, description="Block duration in minutes")

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        trimmed = value.strip()
        if not SAFE_IP_REGEX.match(trimmed):
            raise ValueError(f"IP address '{value}' is not a valid IPv4 or CIDR format")
        return trimmed


ACTION_PARAM_SCHEMAS: dict[AllowlistedActionType, type[BaseModel]] = {
    AllowlistedActionType.ROLLBACK_DEPLOYMENT: RollbackDeploymentParams,
    AllowlistedActionType.RESTART_SERVICE: RestartServiceParams,
    AllowlistedActionType.DRAIN_TRAFFIC: DrainTrafficParams,
    AllowlistedActionType.SCALE_REPLICAS: ScaleReplicasParams,
    AllowlistedActionType.ENABLE_RATE_LIMITING: EnableRateLimitingParams,
    AllowlistedActionType.FLUSH_CACHE: FlushCacheParams,
    AllowlistedActionType.BLOCK_IP: BlockIpParams,
}


class ActionProposalCreate(BaseModel):
    """Schema for proposing a new allowlisted remediation action."""

    action_type: AllowlistedActionType = Field(..., description="Allowlisted action type")
    title: str = Field(..., min_length=3, max_length=250, description="Summary title of the proposed action")
    description: str | None = Field(default=None, max_length=1000)
    parameters: dict[str, Any] = Field(..., description="Strictly typed parameters for the action type")
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM)
    expires_in_minutes: int = Field(default=15, ge=1, le=120, description="TTL in minutes before proposal expires")

    @model_validator(mode="after")
    def validate_parameters_against_action_type(self) -> ActionProposalCreate:
        schema_class = ACTION_PARAM_SCHEMAS.get(self.action_type)
        if schema_class is None:
            raise ValueError(f"Unsupported action type: {self.action_type}")
        try:
            validated = schema_class.model_validate(self.parameters)
            self.parameters = validated.model_dump()
        except Exception as exc:
            raise ValueError(f"Invalid parameters for {self.action_type.value}: {exc}") from exc
        return self


class ActionApprovalRequest(BaseModel):
    """Schema for a human commander approving an action."""

    idempotency_key: str | None = Field(
        default=None,
        description="Optional client-provided idempotency key to protect against network re-submits",
    )
    rationale: str | None = Field(default=None, max_length=500, description="Commander approval justification")


class ActionRejectionRequest(BaseModel):
    """Schema for rejecting an action proposal."""

    reason: str = Field(..., min_length=3, max_length=500, description="Reason for rejection")


class ActionProposalDetail(BaseModel):
    """Public detail view for an action proposal."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    organization_id: UUID
    action_type: AllowlistedActionType
    title: str
    description: str | None = None
    parameters: dict[str, Any]
    risk_level: RiskLevel
    status: str
    idempotency_key: str
    expires_at: datetime
    proposed_by_actor_type: str
    proposed_by_user_id: UUID | None = None
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    execution_result: dict[str, Any] | None = None
    executed_at: datetime | None = None
    created_at: datetime
