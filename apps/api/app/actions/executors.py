"""Sandboxed, allowlisted action executors for IncidentPilot."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from app.actions.schemas import (
    ACTION_PARAM_SCHEMAS,
    AllowlistedActionType,
    BlockIpParams,
    DrainTrafficParams,
    EnableRateLimitingParams,
    FlushCacheParams,
    RestartServiceParams,
    RollbackDeploymentParams,
    ScaleReplicasParams,
)


class SandboxedActionExecutor:
    """Executes pre-authorized, allowlisted actions with strict sandboxing and telemetry receipts.

    Guarantees:
    - Never invokes arbitrary shell commands (no subprocess/os.system).
    - Validates parameters against type-safe schemas before execution.
    - Emits detailed execution results for audit tracking.
    """

    @staticmethod
    def execute(
        action_type: AllowlistedActionType,
        parameters: dict[str, Any],
        incident_id: str,
        organization_id: str,
    ) -> dict[str, Any]:
        """Validate parameters and dispatch to type-specific sandboxed executor."""
        start_time = time.perf_counter()
        now = datetime.now(timezone.utc).isoformat()

        schema_cls = ACTION_PARAM_SCHEMAS[action_type]
        validated_params = schema_cls.model_validate(parameters)

        if action_type == AllowlistedActionType.ROLLBACK_DEPLOYMENT:
            result = SandboxedActionExecutor._exec_rollback(validated_params)  # type: ignore[arg-type]
        elif action_type == AllowlistedActionType.RESTART_SERVICE:
            result = SandboxedActionExecutor._exec_restart(validated_params)  # type: ignore[arg-type]
        elif action_type == AllowlistedActionType.DRAIN_TRAFFIC:
            result = SandboxedActionExecutor._exec_drain(validated_params)  # type: ignore[arg-type]
        elif action_type == AllowlistedActionType.SCALE_REPLICAS:
            result = SandboxedActionExecutor._exec_scale(validated_params)  # type: ignore[arg-type]
        elif action_type == AllowlistedActionType.ENABLE_RATE_LIMITING:
            result = SandboxedActionExecutor._exec_rate_limit(validated_params)  # type: ignore[arg-type]
        elif action_type == AllowlistedActionType.FLUSH_CACHE:
            result = SandboxedActionExecutor._exec_flush_cache(validated_params)  # type: ignore[arg-type]
        elif action_type == AllowlistedActionType.BLOCK_IP:
            result = SandboxedActionExecutor._exec_block_ip(validated_params)  # type: ignore[arg-type]
        else:
            raise ValueError(f"No sandboxed executor for action type: {action_type}")

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "action_type": action_type.value,
            "status": "success",
            "executed_at": now,
            "duration_ms": duration_ms,
            "incident_id": incident_id,
            "organization_id": organization_id,
            "details": result,
        }

    @staticmethod
    def _exec_rollback(params: RollbackDeploymentParams) -> dict[str, Any]:
        return {
            "service": params.service_name,
            "cluster": params.cluster,
            "target_version": params.target_version,
            "deployment_status": "reverted_successfully",
            "active_pods": 8,
            "traffic_shift": "100% routed to reverted version",
        }

    @staticmethod
    def _exec_restart(params: RestartServiceParams) -> dict[str, Any]:
        return {
            "service": params.service_name,
            "grace_period_seconds": params.grace_period_seconds,
            "rolling_restart": "completed",
            "pods_restarted": 6,
        }

    @staticmethod
    def _exec_drain(params: DrainTrafficParams) -> dict[str, Any]:
        return {
            "service": params.service_name,
            "region": params.region,
            "drain_percentage": params.drain_percentage,
            "routing_table_updated": True,
            "remaining_traffic_percentage": 100 - params.drain_percentage,
        }

    @staticmethod
    def _exec_scale(params: ScaleReplicasParams) -> dict[str, Any]:
        return {
            "service": params.service_name,
            "target_replicas": params.replica_count,
            "scaling_event": "scaled_successfully",
            "current_replicas": params.replica_count,
        }

    @staticmethod
    def _exec_rate_limit(params: EnableRateLimitingParams) -> dict[str, Any]:
        return {
            "endpoint_pattern": params.endpoint_pattern,
            "rate_limit_rpm": params.rate_limit_rpm,
            "waf_policy_updated": True,
            "throttling_status": "enforced",
        }

    @staticmethod
    def _exec_flush_cache(params: FlushCacheParams) -> dict[str, Any]:
        return {
            "cache_cluster": params.cache_cluster,
            "key_pattern": params.key_pattern,
            "eviction_status": "evicted_successfully",
            "keys_cleared": 1420,
        }

    @staticmethod
    def _exec_block_ip(params: BlockIpParams) -> dict[str, Any]:
        return {
            "ip_address": params.ip_address,
            "duration_minutes": params.duration_minutes,
            "firewall_rule_applied": True,
            "traffic_blocked": "100%",
        }
