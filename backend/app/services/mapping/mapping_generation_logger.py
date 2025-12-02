"""Logging infrastructure for mapping generation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...utils.logging import get_logger
from ...utils.storage_paths import run_directory
from ...utils.time import isoformat, utc_now


@dataclass
class GenerationLog:
    """Log entry for mapping generation."""
    run_id: str
    question_id: int
    question_number: str
    timestamp: str
    stage: str  # "generation", "validation"
    status: str  # "success", "failed", "pending"
    details: Dict[str, Any]
    mappings_generated: int = 0
    mappings_validated: int = 0
    first_valid_mapping_index: Optional[int] = None
    validation_logs: List[Dict[str, Any]] = field(default_factory=list)


class MappingGenerationLogger:
    """Logger for mapping generation operations."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self._lock = threading.RLock()
        self._logs: Dict[str, List[GenerationLog]] = {}
    
    def log_generation(
        self,
        run_id: str,
        question_id: int,
        question_number: str,
        status: str,
        details: Dict[str, Any],
        mappings_generated: int = 0
    ):
        """Log a generation event."""
        with self._lock:
            logs = self._ensure_loaded_locked(run_id)
            existing = next(
                (log for log in logs if log.question_id == question_id and log.stage == "generation"),
                None,
            )

            timestamp = isoformat(utc_now())

            if existing:
                existing.timestamp = timestamp
                existing.status = status
                existing.details = details
                existing.mappings_generated = mappings_generated
            else:
                log = GenerationLog(
                    run_id=run_id,
                    question_id=question_id,
                    question_number=question_number,
                    timestamp=timestamp,
                    stage="generation",
                    status=status,
                    details=details,
                    mappings_generated=mappings_generated,
                )
                logs.append(log)

            self._save_logs_locked(run_id)
    
    def log_validation(
        self,
        run_id: str,
        question_id: int,
        question_number: str,
        mapping_index: int,
        status: str,
        details: Dict[str, Any]
    ):
        """Log a validation event."""
        with self._lock:
            logs = self._ensure_loaded_locked(run_id)
            generation_log = next(
                (log for log in logs if log.question_id == question_id and log.stage == "generation"),
                None,
            )

            timestamp = isoformat(utc_now())

            entry = {
                "mapping_index": mapping_index,
                "timestamp": timestamp,
                "status": status,
                "details": details,
            }

            if generation_log:
                generation_log.mappings_validated += 1
                generation_log.validation_logs.append(entry)
                if status == "success" and generation_log.first_valid_mapping_index is None:
                    generation_log.first_valid_mapping_index = mapping_index
            else:
                log = GenerationLog(
                    run_id=run_id,
                    question_id=question_id,
                    question_number=question_number,
                    timestamp=timestamp,
                    stage="validation",
                    status=status,
                    details=details,
                    mappings_validated=1,
                    first_valid_mapping_index=mapping_index if status == "success" else None,
                    validation_logs=[entry],
                )
                logs.append(log)

            self._save_logs_locked(run_id)

    def _ensure_loaded_locked(self, run_id: str) -> List[GenerationLog]:
        if run_id in self._logs:
            return self._logs[run_id]

        try:
            run_dir = run_directory(run_id)
            log_file = run_dir / "mapping_generation_logs.json"

            if not log_file.exists():
                self._logs[run_id] = []
                return self._logs[run_id]

            log_data = json.loads(log_file.read_text(encoding="utf-8"))
            logs = [GenerationLog(**log_dict) for log_dict in log_data.get("logs", [])]
            self._logs[run_id] = logs
            return logs
        except Exception as e:
            self.logger.warning(f"Failed to load mapping generation logs: {e}")
            self._logs[run_id] = []
            return self._logs[run_id]

    def _save_logs_locked(self, run_id: str) -> None:
        try:
            run_dir = run_directory(run_id)
            log_file = run_dir / "mapping_generation_logs.json"

            logs = self._logs.get(run_id, [])
            log_data = {
                "run_id": run_id,
                "generated_at": isoformat(utc_now()),
                "logs": [asdict(log) for log in logs],
            }

            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text(json.dumps(log_data, indent=2), encoding="utf-8")
        except Exception as e:
            self.logger.warning(f"Failed to save mapping generation logs: {e}")
    
    def get_logs(self, run_id: str) -> List[Dict[str, Any]]:
        """Get logs for a run as dictionaries."""
        with self._lock:
            logs = self._ensure_loaded_locked(run_id)
            return [asdict(log) for log in logs]
    
    def get_question_logs(self, run_id: str, question_id: int) -> List[Dict[str, Any]]:
        """Get logs for a specific question."""
        with self._lock:
            logs = self._ensure_loaded_locked(run_id)
            question_logs = [log for log in logs if log.question_id == question_id]
            return [asdict(log) for log in question_logs]

    def load_logs(self, run_id: str, *, force: bool = False) -> List[GenerationLog]:
        """Public loader that optionally forces a refresh from disk."""
        with self._lock:
            if force and run_id in self._logs:
                del self._logs[run_id]
            return list(self._ensure_loaded_locked(run_id))


# Global logger instance
_mapping_logger = None


def get_mapping_logger() -> MappingGenerationLogger:
    """Get global mapping generation logger."""
    global _mapping_logger
    if _mapping_logger is None:
        _mapping_logger = MappingGenerationLogger()
    return _mapping_logger

