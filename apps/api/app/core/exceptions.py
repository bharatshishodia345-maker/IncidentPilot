"""Domain exceptions for IncidentPilot application boundaries."""

from __future__ import annotations


class IncidentPilotException(Exception):
    """Base exception for all IncidentPilot domain errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EntityNotFoundError(IncidentPilotException):
    """Raised when a requested resource cannot be found in the tenant's scope."""

    def __init__(self, entity_name: str, identifier: str) -> None:
        super().__init__(f"{entity_name} with identifier '{identifier}' was not found")
        self.entity_name = entity_name
        self.identifier = identifier


class PermissionDeniedError(IncidentPilotException):
    """Raised when an authenticated principal attempts an unauthorized action."""

    def __init__(self, message: str = "Insufficient permissions for this operation") -> None:
        super().__init__(message)


class ConflictError(IncidentPilotException):
    """Raised when a resource state conflicts with the requested operation."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidStateTransitionError(ConflictError):
    """Raised when attempting an invalid status transition on an incident."""

    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(f"Cannot transition incident status from '{current_status}' to '{target_status}'")
        self.current_status = current_status
        self.target_status = target_status


class DatabaseConnectionError(IncidentPilotException):
    """Raised when database connectivity fails during an operation."""

    def __init__(self, message: str = "Database service is temporarily unavailable") -> None:
        super().__init__(message)
