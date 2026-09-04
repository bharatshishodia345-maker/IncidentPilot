"""Configuration loaded from environment variables and an optional local .env file."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings.

    SQLite is deliberately allowed only for local development and tests. A
    deployed environment must supply a PostgreSQL connection string and JWT
    secret through its secret manager or process environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "IncidentPilot"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    database_url: str = "sqlite+pysqlite:///./incidentpilot.db"
    cors_origins: list[str] = []
    log_level: str = "INFO"

    # Database connection pool tuning (applicable to PostgreSQL)
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    jwt_secret: SecretStr | None = None
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "incidentpilot"
    jwt_audience: str = "incidentpilot-api"
    allow_dev_persona_auth: bool = True

    # Agora Real-Time Voice Configuration
    agora_app_id: str | None = None
    agora_app_certificate: SecretStr | None = None
    agora_token_expire_seconds: int = 3600

    # External Integration Tokens (optional/overridable via environment)
    slack_bot_token: SecretStr | None = None
    jira_base_url: str | None = None
    jira_api_token: SecretStr | None = None
    monitoring_api_key: SecretStr | None = None

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper().strip()
        if normalized not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(valid_levels)}")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DATABASE_URL must not be empty")
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        secret = value.get_secret_value()
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_deployed_settings(self) -> "Settings":
        if self.environment is Environment.PRODUCTION:
            if self.database_url.startswith("sqlite"):
                raise ValueError("production requires a PostgreSQL DATABASE_URL")
            if self.jwt_secret is None or not self.jwt_secret.get_secret_value():
                raise ValueError("production requires JWT_SECRET")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origin '*' is prohibited in production")
            if not self.cors_origins:
                raise ValueError("production requires explicit CORS_ORIGINS")
        return self

    def get_effective_jwt_secret(self) -> str:
        """Return configured JWT secret, or a safe fallback for development/test."""
        if self.jwt_secret is not None and self.jwt_secret.get_secret_value():
            return self.jwt_secret.get_secret_value()
        if self.environment in (Environment.DEVELOPMENT, Environment.TEST):
            return "dev-incidentpilot-local-environment-signing-key-32bytes"
        raise ValueError("production requires JWT_SECRET")

    def sanitized_dict(self) -> dict[str, object]:
        """Return configuration dictionary safe for diagnostic logging (secrets redacted)."""
        data = self.model_dump()
        for secret_key in [
            "jwt_secret",
            "agora_app_certificate",
            "slack_bot_token",
            "jira_api_token",
            "monitoring_api_key",
        ]:
            if data.get(secret_key) is not None:
                data[secret_key] = "**********"
        return data


@lru_cache
def get_settings() -> Settings:
    """Return process-level settings; tests should inject Settings explicitly."""
    return Settings()
