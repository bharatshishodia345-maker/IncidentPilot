from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.dependencies import Principal, require_roles
from app.config import Environment, Settings
from app.db.models import UserRole
from app.main import create_app


def test_me_accepts_a_token_with_required_incident_claims(tmp_path) -> None:
    secret = "test-only-signing-secret-at-least-32-bytes"
    organization_id = uuid4()
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'auth.db'}",
        jwt_secret=secret,
    )
    token = jwt.encode(
        {
            "sub": "auth0|commander",
            "org_id": str(organization_id),
            "role": UserRole.INCIDENT_COMMANDER.value,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "subject": "auth0|commander",
        "organization_id": str(organization_id),
        "role": UserRole.INCIDENT_COMMANDER.value,
    }


def test_commander_guard_rejects_a_responder() -> None:
    guard = require_roles(UserRole.INCIDENT_COMMANDER)
    responder = Principal(subject="auth0|responder", organization_id=uuid4(), role=UserRole.RESPONDER)

    with pytest.raises(HTTPException) as exc_info:
        guard(responder)

    assert exc_info.value.status_code == 403


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(environment=Environment.TEST, jwt_secret="too-short")


def test_personas_and_token_endpoint(tmp_path) -> None:
    secret = "test-only-signing-secret-at-least-32-bytes"
    settings = Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'personas.db'}",
        jwt_secret=secret,
    )
    from sqlalchemy import create_engine
    from app.db.base import Base
    from app.db.seed import seed_dev_database
    from app.db.session import configure_database

    engine = configure_database(settings.database_url)
    Base.metadata.create_all(engine)

    with TestClient(create_app(settings)) as client:
        # Test personas listing
        resp = client.get("/v1/identity/personas")
        assert resp.status_code == 200
        personas = resp.json()
        assert len(personas) >= 3
        roles = {p["role"] for p in personas}
        assert "incident_commander" in roles
        assert "responder" in roles

        # Test token generation for commander
        token_resp = client.post("/v1/identity/token", json={"role": "incident_commander"})
        assert token_resp.status_code == 200
        token_data = token_resp.json()
        assert "access_token" in token_data
        token = token_data["access_token"]

        # Verify token against /me
        me_resp = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["role"] == "incident_commander"

