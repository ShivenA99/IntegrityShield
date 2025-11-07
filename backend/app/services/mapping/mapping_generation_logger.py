"""Logging infrastructure for mapping generation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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
        log = GenerationLog(
            run_id=run_id,
            question_id=question_id,
            question_number=question_number,
            timestamp=isoformat(utc_now()),
            stage="generation",
            status=status,
            details=details,
            mappings_generated=mappings_generated
        )
        self._add_log(run_id, log)
        self._save_logs(run_id)
    
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
        # Find or create generation log
        logs = self._get_logs(run_id)
        generation_log = None
        for log in logs:
            if log.question_id == question_id and log.stage == "generation":
                generation_log = log
                break
        
        if generation_log:
            generation_log.mappings_validated += 1
            generation_log.validation_logs.append({
                "mapping_index": mapping_index,
                "timestamp": isoformat(utc_now()),
                "status": status,
                "details": details
            })
            if status == "success" and generation_log.first_valid_mapping_index is None:
                generation_log.first_valid_mapping_index = mapping_index
        else:
            # Create new validation log
            log = GenerationLog(
                run_id=run_id,
                question_id=question_id,
                question_number=question_number,
                timestamp=isoformat(utc_now()),
                stage="validation",
                status=status,
                details=details,
                mappings_validated=1,
                first_valid_mapping_index=mapping_index if status == "success" else None,
                validation_logs=[{
                    "mapping_index": mapping_index,
                    "timestamp": isoformat(utc_now()),
                    "status": status,
                    "details": details
                }]
            )
            self._add_log(run_id, log)
        
        self._save_logs(run_id)
    
    def _add_log(self, run_id: str, log: GenerationLog):
        """Add log to in-memory storage."""
        if run_id not in self._logs:
            self._logs[run_id] = []
        self._logs[run_id].append(log)
    
    def _get_logs(self, run_id: str) -> List[GenerationLog]:
        """Get logs for a run."""
        return self._logs.get(run_id, [])
    
    def _save_logs(self, run_id: str):
        """Save logs to disk."""
        try:
            run_dir = run_directory(run_id)
            log_file = run_dir / "mapping_generation_logs.json"
            
            logs = self._get_logs(run_id)
            log_data = {
                "run_id": run_id,
                "generated_at": isoformat(utc_now()),
                "logs": [asdict(log) for log in logs]
            }
            
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text(json.dumps(log_data, indent=2), encoding="utf-8")
        except Exception as e:
            self.logger.warning(f"Failed to save mapping generation logs: {e}")
    
    def get_logs(self, run_id: str) -> List[Dict[str, Any]]:
        """Get logs for a run as dictionaries."""
        logs = self._get_logs(run_id)
        return [asdict(log) for log in logs]
    
    def get_question_logs(self, run_id: str, question_id: int) -> List[Dict[str, Any]]:
        """Get logs for a specific question."""
        logs = self._get_logs(run_id)
        question_logs = [log for log in logs if log.question_id == question_id]
        return [asdict(log) for log in question_logs]
    
    def load_logs(self, run_id: str) -> List[GenerationLog]:
        """Load logs from disk."""
        try:
            run_dir = run_directory(run_id)
            log_file = run_dir / "mapping_generation_logs.json"
            
            if not log_file.exists():
                return []
            
            log_data = json.loads(log_file.read_text(encoding="utf-8"))
            logs = []
            for log_dict in log_data.get("logs", []):
                log = GenerationLog(**log_dict)
                logs.append(log)
            
            self._logs[run_id] = logs
            return logs
        except Exception as e:
            self.logger.warning(f"Failed to load mapping generation logs: {e}")
            return []


# Global logger instance
_mapping_logger = None


def get_mapping_logger() -> MappingGenerationLogger:
    """Get global mapping generation logger."""
    global _mapping_logger
    if _mapping_logger is None:
        _mapping_logger = MappingGenerationLogger()
    return _mapping_logger

