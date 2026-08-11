"""Logging configuration for the Nuotao AI OS backend."""

import logging
import sys

from app.core.config import get_settings

_QUIET_LOGGERS: tuple[str, ...] = (
    "uvicorn.access",
    "watchfiles",
)


def setup_logging() -> None:
    """Configure the root logger with a consistent console format.

    Call once at application startup, before any module emits logs.
    """
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
