"""Authenticated identity boundary and persona session token management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import Principal, get_current_principal
from app.config import Environment, Settings, get_settings
from app.db.models import Organization, User, UserRole
from app.db.seed import DEFAULT_ORG_ID, seed_dev_database
from app.db.session import get_db

router = APIRouter(tags=["identity"])


class PersonaDetail(BaseModel):
    user_id: UUID
    organization_id: UUID
    display_name: str
    email: str
    role: UserRole
    subject: str


class TokenRequest(BaseModel):
    role: UserRole = Field(default=UserRole.INCIDENT_COMMANDER, description="Requested role")
    user_id: UUID | None = Field(default=None, description="Optional specific user UUID")
    organization_id: UUID | None = Field(default=None, description="Optional organization UUID")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int = 3600
    principal: Principal
    display_name: str
    email: str


@router.get("/me", response_model=Principal, response_model_exclude_none=True)
def get_me(principal: Principal = Depends(get_current_principal)) -> Principal:
    """Return the validated identity claims, never the raw JWT."""
    return principal


@router.get("/identity/personas", response_model=list[PersonaDetail])
def list_personas(
    request: Request,
    session: Session = Depends(get_db),
) -> list[PersonaDetail]:
    """List available personas for local development and war room role-switching."""
    settings: Settings = getattr(request.app.state, "settings", get_settings())
    if settings.environment == Environment.PRODUCTION and not settings.allow_dev_persona_auth:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Persona listing is disabled in production",
        )

    users = list(session.scalars(select(User).order_by(User.role.asc())).all())
    if not users:
        seed_result = seed_dev_database(session)
        users = [
            seed_result["commander"],
            seed_result["responder"],
            seed_result["observer"],
        ]

    return [
        PersonaDetail(
            user_id=u.id,
            organization_id=u.organization_id,
            display_name=u.display_name,
            email=u.email,
            role=u.role,
            subject=u.subject,
        )
        for u in users
    ]


@router.post("/identity/token", response_model=TokenResponse)
def generate_persona_token(
    payload: TokenRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> TokenResponse:
    """Issue a signed JWT token for the specified persona / role in local development."""
    settings: Settings = getattr(request.app.state, "settings", get_settings())

    if settings.environment == Environment.PRODUCTION and not settings.allow_dev_persona_auth:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development persona token generation is disabled in production",
        )

    try:
        secret = settings.get_effective_jwt_secret()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        )

    # 1. Resolve user from database
    statement = select(User)
    if payload.user_id is not None:
        statement = statement.where(User.id == payload.user_id)
    elif payload.role is not None:
        statement = statement.where(User.role == payload.role)
    if payload.organization_id is not None:
        statement = statement.where(User.organization_id == payload.organization_id)

    user = session.scalar(statement)
    if user is None:
        # If DB is empty, run seeder
        seed_dev_database(session)
        user = session.scalar(statement)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No persona found for role={payload.role.value}",
        )

    # 2. Build claims & sign JWT
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(seconds=3600)
    claims = {
        "sub": user.subject,
        "org_id": str(user.organization_id),
        "role": user.role.value,
        "user_id": str(user.id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "exp": now + expires_delta,
    }

    token = jwt.encode(claims, secret, algorithm=settings.jwt_algorithm)

    principal = Principal(
        subject=user.subject,
        organization_id=user.organization_id,
        role=user.role,
        user_id=user.id,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=3600,
        principal=principal,
        display_name=user.display_name,
        email=user.email,
    )
