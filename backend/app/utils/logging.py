from __future__ import annotations

import logging
import os
from typing import Any

from pythonjsonlogger import jsonlogger
import structlog


def configure_logging(app: Any | None = None) -> None:
    """Configure application-wide logging using structlog."""
    log_level = (app.config.get("LOG_LEVEL") if app else os.getenv("FAIRTESTAI_LOG_LEVEL")) or "INFO"

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)

    # Replace existing handlers to avoid duplicate logs during reloads
    root_logger.handlers = [handler]

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
