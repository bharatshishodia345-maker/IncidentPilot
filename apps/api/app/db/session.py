"""Database engine and request-session lifecycle management."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _engine_options(database_url: str) -> dict[str, object]:
    settings = get_settings()
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            options["poolclass"] = StaticPool
    else:
        options["pool_size"] = settings.db_pool_size
        options["max_overflow"] = settings.db_max_overflow
        options["pool_timeout"] = settings.db_pool_timeout
        options["pool_recycle"] = settings.db_pool_recycle
    return options


def configure_database(database_url: str) -> Engine:
    """Configure the process database connection from an explicit URL.

    The application uses a single process-wide engine for the MVP. Tests call
    this function with a temporary SQLite database; deployed environments use
    PostgreSQL supplied through DATABASE_URL.
    """

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()

    _engine = create_engine(database_url, **_engine_options(database_url))
    _session_factory = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return configure_database(get_settings().database_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that commits nothing implicitly."""

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def dispose_database() -> None:
    """Release engine resources during application shutdown and tests."""

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None

