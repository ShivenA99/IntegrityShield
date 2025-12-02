from __future__ import annotations

import logging
import os
from typing import Any

from pythonjsonlogger import jsonlogger
import structlog


def configure_logging(app: Any | None = None) -> None:
    """Configure application-wide logging using structlog."""
    log_level = (app.config.get("LOG_LEVEL") if app else os.getenv("INTEGRITYSHIELD_LOG_LEVEL")) or "INFO"

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


def configure_pipeline_logging(app: Any) -> None:
    """Configure file-based logging for background pipeline execution."""
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    # Create logs directory
    base_dir = Path(app.config.get("BASE_DIR", Path.cwd()))
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create rotating file handler
    log_file = log_dir / "pipeline_execution.log"
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=10_000_000,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(name)s - %(levelname)s - %(message)s"
    ))

    # Add to pipeline-related loggers
    pipeline_logger = logging.getLogger("app.services.pipeline")
    pipeline_logger.addHandler(file_handler)
    pipeline_logger.setLevel(logging.DEBUG)

    app.logger.info(f"Pipeline logging configured: {log_file}")
