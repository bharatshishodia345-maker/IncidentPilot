from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Environment, Settings
from app.db.base import Base
from app.db.models import Organization, User, UserRole
from app.main import create_app

TEST_SECRET = "test-only-signing-secret-at-least-32-bytes"


def generate_jwt(
    organization_id: UUID,
    role: UserRole,
    subject: str = "auth0|user",
    user_id: UUID | None = None,
    secret: str = TEST_SECRET,
    issuer: str = "incidentpilot",
    audience: str = "incidentpilot-api",
    expires_in_minutes: int = 15,
) -> str:
    payload = {
        "sub": subject,
        "org_id": str(organization_id),
        "role": role.value,
        "iss": issuer,
        "aud": audience,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
    }
    if user_id is not None:
        payload["user_id"] = str(user_id)
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        environment=Environment.TEST,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        jwt_secret=TEST_SECRET,
        log_level="DEBUG",
    )


@pytest.fixture
def test_app(test_settings):
    # Ensure tables exist in the test db
    engine = create_engine(test_settings.database_url)
    Base.metadata.create_all(engine)
    app = create_app(test_settings)
    yield app
    engine.dispose()


@pytest.fixture
def client(test_app):
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def seed_data(test_settings):
    """Seed test database with two organizations and associated users."""
    engine = create_engine(test_settings.database_url)
    with Session(engine) as db:
        org1 = Organization(name="Primary Org")
        org2 = Organization(name="Secondary Org")
        db.add_all([org1, org2])
        db.flush()

        commander = User(
            organization_id=org1.id,
            subject="auth0|commander-1",
            email="commander@primary.test",
            display_name="Primary Commander",
            role=UserRole.INCIDENT_COMMANDER,
        )
        responder = User(
            organization_id=org1.id,
            subject="auth0|responder-1",
            email="responder@primary.test",
            display_name="Primary Responder",
            role=UserRole.RESPONDER,
        )
        observer = User(
            organization_id=org1.id,
            subject="auth0|observer-1",
            email="observer@primary.test",
            display_name="Primary Observer",
            role=UserRole.OBSERVER,
        )
        other_commander = User(
            organization_id=org2.id,
            subject="auth0|commander-2",
            email="commander@secondary.test",
            display_name="Secondary Commander",
            role=UserRole.INCIDENT_COMMANDER,
        )
        db.add_all([commander, responder, observer, other_commander])
        db.commit()

        yield {
            "org1": org1,
            "org2": org2,
            "commander": commander,
            "responder": responder,
            "observer": observer,
            "other_commander": other_commander,
        }
    engine.dispose()
