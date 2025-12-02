from __future__ import annotations

import queue
import threading
from collections import defaultdict, deque
from typing import Deque, Dict, Generator, Optional

from flask import current_app

from ...extensions import db
from ...models import PipelineLog
from ...utils.logging import get_logger


_log_streams: Dict[str, "queue.Queue[dict]"] = defaultdict(queue.Queue)
_buffered_logs: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=200))
_lock = threading.Lock()


class LiveLoggingService:
    """Persist pipeline log entries and broadcast them to websocket clients."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    def emit(
        self,
        run_id: str,
        stage: str,
        level: str,
        message: str,
        component: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> None:
        log_record = PipelineLog(
            pipeline_run_id=run_id,
            stage=stage,
            level=level.upper(),
            message=message,
            component=component,
            context=context or {},
        )
        try:
            db.session.add(log_record)
            db.session.commit()
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            self.logger.warning(
                "live log commit failed",
                extra={"run_id": run_id, "stage": stage, "component": component, "error": str(exc)},
                exc_info=True,
            )

        payload = {
            "id": log_record.id,
            "timestamp": log_record.timestamp.isoformat() if log_record.timestamp else None,
            "stage": stage,
            "level": log_record.level,
            "component": component,
            "message": message,
            "metadata": context or {},
        }

        with _lock:
            _buffered_logs[run_id].appendleft(payload)
        _log_streams[run_id].put(payload)

    def stream_logs(self, run_id: str) -> Generator[dict, None, None]:
        # Yield buffered history first
        with _lock:
            buffered = list(_buffered_logs[run_id])

        for event in buffered:
            yield event

        queue_ref = _log_streams[run_id]
        while True:
            try:
                event = queue_ref.get(timeout=current_app.config.get("LOG_STREAM_TIMEOUT", 30))
                yield event
            except queue.Empty:
                # Keep connection alive with ping messages
                yield {"type": "ping"}


live_logging_service = LiveLoggingService()
