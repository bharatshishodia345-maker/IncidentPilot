from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Environment, Settings


def test_valid_settings_defaults() -> None:
    settings = Settings(environment=Environment.DEVELOPMENT)
    assert settings.app_name == "IncidentPilot"
    assert settings.app_version == "0.1.0"
    assert settings.log_level == "INFO"
    assert settings.db_pool_size == 10



def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError, match="LOG_LEVEL must be one of"):
        Settings(environment=Environment.DEVELOPMENT, log_level="INVALID_LEVEL")


def test_production_requires_postgres_and_secret() -> None:
    # Fails if database_url is sqlite in production
    with pytest.raises(ValidationError, match="requires a PostgreSQL DATABASE_URL"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="sqlite+pysqlite:///./test.db",
            jwt_secret="at-least-32-characters-long-secret-key-12345",
            cors_origins=["https://incidentpilot.company.com"],
        )

    # Fails if jwt_secret is missing in production
    with pytest.raises(ValidationError, match="production requires JWT_SECRET"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+psycopg://user:pass@localhost:5432/db",
            jwt_secret=None,
            cors_origins=["https://incidentpilot.company.com"],
        )

    # Fails if wildcard CORS is specified in production
    with pytest.raises(ValidationError, match="Wildcard CORS origin"):
        Settings(
            environment=Environment.PRODUCTION,
            database_url="postgresql+psycopg://user:pass@localhost:5432/db",
            jwt_secret="at-least-32-characters-long-secret-key-12345",
            cors_origins=["*"],
        )


def test_sanitized_dict_redacts_secrets() -> None:
    settings = Settings(
        environment=Environment.DEVELOPMENT,
        jwt_secret="super-secret-key-at-least-32-chars-long",
        agora_app_certificate="agora-secret-cert-12345",
    )
    sanitized = settings.sanitized_dict()
    assert sanitized["jwt_secret"] == "**********"
    assert sanitized["agora_app_certificate"] == "**********"

