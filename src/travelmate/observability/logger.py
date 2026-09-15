"""Structured logging configuration using structlog.

Provides JSON formatted logs in production and human-readable logs in development,
enriching log records with timestamps, log levels, and correlation IDs.
"""

from __future__ import annotations

import logging
import sys

import structlog

from src.travelmate.config import settings


def configure_logging() -> None:
    """Configure structlog and standard library logging handlers."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.app_env == "production":
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=False),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger instance bound to a module name.

    Args:
        name: Name of module or component.

    Returns:
        Configured BoundLogger instance.
    """
    return structlog.get_logger(name)
