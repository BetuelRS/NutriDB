"""Structured logging setup for the nutridb CLI."""

from __future__ import annotations

import logging
import sys

import structlog

__all__ = ["configure_logging"]


def configure_logging(*, verbosity: int = 0) -> None:
    """Configure structlog at the given verbosity (0 = info, 1 = debug, 2 = trace)."""
    level = logging.DEBUG if verbosity > 0 else logging.INFO
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
