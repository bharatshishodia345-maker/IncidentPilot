"""JWT verification and reusable RBAC dependencies.

This module verifies credentials issued by the configured identity provider. It
does not provide a login endpoint or create tokens, which keeps identity
provisioning outside the MVP foundation until a provider is selected.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.db.models import UserRole

bearer_scheme = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    subject: str
    organization_id: UUID
    role: UserRole
    user_id: UUID | None = None


def _settings_from_request(request: Request) -> Settings:
    return request.app.state.settings


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    """Validate the minimally required incident-scoped JWT claims."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    settings = _settings_from_request(request)
    try:
        secret = settings.get_effective_jwt_secret()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        )

    try:
        claims = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "org_id", "role"]},
        )
        raw_user_id = claims.get("user_id")
        parsed_user_id = UUID(str(raw_user_id)) if raw_user_id is not None else None

        return Principal(
            subject=claims["sub"],
            organization_id=claims["org_id"],
            role=claims["role"],
            user_id=parsed_user_id,
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError, ValidationError):
        raise _unauthorized() from None


def require_roles(*allowed_roles: UserRole) -> Callable[[Principal], Principal]:
    """Return a dependency that permits only explicitly listed roles."""

    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient permissions",
            )
        return principal

    return dependency

