"""Application middlewares for request tracing and security headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Environment, get_settings
from app.core.logging import get_logger

logger = get_logger("app.middleware")


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Assign or propagate X-Request-ID and attach strict security response headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()
        response: Response = await call_next(request)
        process_time_ms = (time.perf_counter() - start_time) * 1000

        # Security Headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        settings = get_settings()
        if settings.environment == Environment.PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Log completion at debug/info without exposing credentials or payload bodies
        if not request.url.path.startswith("/health"):
            logger.info(
                "%s %s -> %s (%.2fms)",
                request.method,
                request.url.path,
                response.status_code,
                process_time_ms,
                extra={"request_id": request_id},
            )
        return response
