from __future__ import annotations

import logging
import os

from app_logger import AppLogger, create_logger, resolve_level

_root_logger: AppLogger | None = None


def configure_logging(*, component: str = "api") -> AppLogger:
    """Configure structured JSON logging for one process.

    Silences uvicorn's own access log so the only request lines are the
    structured ones emitted by RequestLoggingMiddleware.
    """
    global _root_logger

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    _root_logger = create_logger(
        level=resolve_level(os.getenv("LOG_LEVEL")),
        base_context={
            "component": component,
            "service": component,
            "env": os.getenv("APP_ENV", "development"),
        },
    )
    return _root_logger


def get_logger() -> AppLogger:
    return _root_logger if _root_logger is not None else configure_logging()
