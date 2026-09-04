"""Structured, secure logging setup for IncidentPilot."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


class IncidentPilotFormatter(logging.Formatter):
    """Standardized log formatter that avoids leaking sensitive headers or tokens."""

    def format(self, record: logging.LogRecord) -> str:
        # Provide default request_id attribute if not set
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return super().format(record)


def setup_logging(settings: Settings) -> None:
    """Configure root and application loggers based on environment settings."""
    log_level = getattr(logging, settings.log_level, logging.INFO)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers on re-initialization
    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        formatter = IncidentPilotFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] [req_id=%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            handler.setLevel(log_level)

    # Set third-party logger noise levels
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger instance."""
    return logging.getLogger(name)
