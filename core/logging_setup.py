"""
Structured logging configuration using structlog + standard library.
"""
import logging
import sys
from pathlib import Path

import structlog

from core.config import settings


def setup_logging():
    """Configure structlog for both console (rich) and file output."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_file = Path(settings.log_dir) / "agents.log"

    # Standard library logging
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception as e:
        print(f"Warning: Could not open log file {log_file}: {e}")

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=handlers,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer() if sys.stdout.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
