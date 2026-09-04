"""Centralized exception handlers for FastAPI."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    ConflictError,
    DatabaseConnectionError,
    EntityNotFoundError,
    IncidentPilotException,
    PermissionDeniedError,
)
from app.core.logging import get_logger

logger = get_logger("app.errors")


def register_error_handlers(app: FastAPI) -> None:
    """Attach structured error handlers to the FastAPI application instance."""

    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.message, "code": "NOT_FOUND"},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(request: Request, exc: PermissionDeniedError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message, "code": "PERMISSION_DENIED"},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message, "code": "CONFLICT"},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(DatabaseConnectionError)
    async def db_connection_error_handler(request: Request, exc: DatabaseConnectionError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        logger.error("Database connection failure: %s", exc.message, extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Database is currently unavailable", "code": "DATABASE_UNAVAILABLE"},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        errors = []
        for error in exc.errors():
            loc = " -> ".join(str(loc_item) for loc_item in error.get("loc", []))
            errors.append({"field": loc, "message": error.get("msg", "Invalid value")})

        status_code = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
        return JSONResponse(
            status_code=status_code,
            content={

                "detail": "Request validation failed",
                "code": "VALIDATION_ERROR",
                "errors": errors,
            },
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        logger.warning("Database integrity constraint violated: %s", str(exc.orig), extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Data integrity conflict occurred", "code": "INTEGRITY_CONFLICT"},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        logger.error("Unhandled database error: %s", str(exc), extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Database service error", "code": "DATABASE_ERROR"},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": "HTTP_ERROR"},
            headers={"X-Request-ID": request_id, **(exc.headers or {})},
        )

    from app.integrations.base import IntegrationError

    @app.exception_handler(IntegrationError)
    async def integration_error_handler(request: Request, exc: IntegrationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code, "provider": exc.provider},
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(IncidentPilotException)
    async def domain_exception_handler(request: Request, exc: IncidentPilotException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.message, "code": "DOMAIN_ERROR"},
            headers={"X-Request-ID": request_id},
        )


    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        logger.exception("Unhandled server exception: %s", str(exc), extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred", "code": "INTERNAL_SERVER_ERROR"},
            headers={"X-Request-ID": request_id},
        )
