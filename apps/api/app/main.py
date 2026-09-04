"""FastAPI application composition root."""

from __future__ import annotations

import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestCorrelationMiddleware
from app.db.session import configure_database, dispose_database

STATIC_DIR = pathlib.Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application without applying migrations or creating tables."""
    application_settings = settings or get_settings()
    setup_logging(application_settings)
    configure_database(application_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        from app.config import Environment

        if application_settings.environment in (Environment.DEVELOPMENT, Environment.TEST):
            # Auto-run migrations so `uvicorn apps/api/...` works without a separate step
            try:
                import pathlib as _pl
                from alembic import command as _alembic_cmd
                from alembic.config import Config as _AlembicConfig

                # Locate alembic.ini relative to this package root (works from any cwd)
                _pkg_root = _pl.Path(__file__).parent.parent  # apps/api/
                _project_root = _pkg_root.parent.parent       # IncidentPilot/
                _ini = _project_root / "alembic.ini"
                if _ini.exists():
                    _cfg = _AlembicConfig(str(_ini))
                    _alembic_cmd.upgrade(_cfg, "head")
            except Exception as _mig_err:
                import logging as _log
                _log.getLogger(__name__).warning("Auto-migration skipped: %s", _mig_err)

            try:
                from app.db.seed import seed_dev_database
                from app.db.session import get_session_factory
                with get_session_factory()() as db_session:
                    seed_dev_database(db_session)
            except Exception as _seed_err:
                import logging as _log
                _log.getLogger(__name__).warning("Dev seed skipped: %s", _seed_err)

        yield
        dispose_database()

    application = FastAPI(
        title=application_settings.app_name,
        version=application_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = application_settings

    # Middlewares (executed in reverse order of addition)
    application.add_middleware(RequestCorrelationMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=application_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # Register centralized exception handlers
    register_error_handlers(application)

    # Mount API routers
    application.include_router(api_router)

    # Mount Static Files & War Room Frontend
    if STATIC_DIR.exists():
        application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @application.get("/", include_in_schema=False)
        def serve_war_room():
            return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()
