"""Unauthenticated health, liveness, and readiness endpoints for orchestration and diagnostics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.schemas import HealthResponse
from app.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
@router.get("/healthz", response_model=HealthResponse, include_in_schema=False)
def health_check(
    request: Request,
    session: Session = Depends(get_db),
) -> HealthResponse:
    """Confirm the API is healthy and database is connected."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from None

    settings = getattr(request.app.state, "settings", get_settings())

    return HealthResponse(
        status="ok",
        database="ok",
        version=settings.app_version,
        environment=settings.environment.value,
    )


@router.get("/health/live")
def liveness_probe() -> dict[str, str]:
    """Kubernetes liveness probe: returns 200 if the container process is responsive."""
    return {"status": "alive"}


@router.get("/health/ready")
def readiness_probe(session: Session = Depends(get_db)) -> dict[str, str]:
    """Kubernetes readiness probe: confirms database is reachable before accepting traffic."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unreachable",
        ) from None
    return {"status": "ready"}
