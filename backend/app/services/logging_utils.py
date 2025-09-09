import logging
import contextvars
from pathlib import Path
from typing import Optional

# Context variable to inject per-run id into log records
_run_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="-")


class RunContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            record.run_id = _run_id_var.get()
        except Exception:
            record.run_id = "-"
        return True


def activate_run_context(run_id: str) -> None:
    """Activate a run context so logs include run_id."""
    try:
        _run_id_var.set(str(run_id))
    except Exception:
        pass


def create_run_file_handler(log_path: Path, level: int = logging.DEBUG) -> logging.Handler:
    """Create a file handler configured with our run-id filter and formatter."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
    handler.setLevel(level)
    handler.addFilter(RunContextFilter())
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)5s | %(name)s:%(lineno)d | run=%(run_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    return handler


def attach_run_file_handler(handler: logging.Handler, *, logger: Optional[logging.Logger] = None) -> None:
    """Attach the handler to the specified logger (or root logger by default)."""
    target_logger = logger or logging.getLogger()
    # Avoid duplicate attachment of the same handler
    if handler not in target_logger.handlers:
        target_logger.addHandler(handler)


def detach_run_file_handler(handler: logging.Handler, *, logger: Optional[logging.Logger] = None) -> None:
    """Detach and close the given handler from the logger (or root)."""
    try:
        target_logger = logger or logging.getLogger()
        if handler in target_logger.handlers:
            target_logger.removeHandler(handler)
        try:
            handler.flush()
        except Exception:
            pass
        try:
            handler.close()
        except Exception:
            pass
    except Exception:
        pass 