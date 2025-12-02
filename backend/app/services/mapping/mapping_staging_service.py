"""Staging utilities for mapping generation results."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ...models import QuestionManipulation
from ...utils.logging import get_logger
from ...utils.storage_paths import run_directory
from ...utils.time import isoformat, utc_now


class MappingStagingService:
    """Persist and manage staged mappings prior to final promotion."""

    _lock = threading.RLock()

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load(self, run_id: str) -> Dict[str, Any]:
        with self._lock:
            path = self._stage_path(run_id)
            if not path.exists():
                return {
                    "run_id": run_id,
                    "questions": {},
                    "updated_at": None,
                }

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                self.logger.warning("Failed to parse staging file", extra={"run_id": run_id, "error": str(exc)})
                return {
                    "run_id": run_id,
                    "questions": {},
                    "updated_at": None,
                }

            data.setdefault("questions", {})
            return data

    def stage_valid_mapping(
        self,
        run_id: str,
        question: QuestionManipulation,
        substring_mapping: Dict[str, Any],
        *,
        generated_count: int,
        validation_logs: Iterable[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = metadata or {}
        logs_list = list(validation_logs or [])
        summary = self._extract_validation_summary(logs_list)

        mapping_payload = json.loads(json.dumps(substring_mapping))
        if summary:
            mapping_payload.setdefault("validated", True)
            if "confidence" in summary:
                mapping_payload.setdefault("confidence", summary.get("confidence"))
            if "deviation_score" in summary:
                mapping_payload.setdefault("deviation_score", summary.get("deviation_score"))
            if "reasoning" in summary:
                mapping_payload.setdefault("validation_reasoning", summary.get("reasoning"))

        entry = {
            "question_id": question.id,
            "question_number": str(question.question_number),
            "sequence_index": question.sequence_index,
            "source_identifier": question.source_identifier,
            "status": "validated",
            "job_id": metadata.get("job_id"),
            "generated_count": generated_count,
            "validated_count": len(logs_list),
            "staged_mapping": mapping_payload,
            "validation_logs": logs_list,
            "validation_summary": summary,
            "strategy": metadata.get("strategy"),
            "updated_at": isoformat(utc_now()),
        }

        self._persist_entry(run_id, question.id, entry)

    def stage_no_valid_mapping(
        self,
        run_id: str,
        question: QuestionManipulation,
        *,
        generated_count: int,
        validation_logs: Iterable[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = metadata or {}
        logs_list = list(validation_logs or [])

        entry = {
            "question_id": question.id,
            "question_number": str(question.question_number),
            "sequence_index": question.sequence_index,
            "source_identifier": question.source_identifier,
            "status": "no_valid_mapping",
            "job_id": metadata.get("job_id"),
            "generated_count": generated_count,
            "validated_count": len(logs_list),
            "validation_logs": logs_list,
            "skip_reason": metadata.get("skip_reason", "No valid mapping produced"),
            "updated_at": isoformat(utc_now()),
        }

        self._persist_entry(run_id, question.id, entry)

    def stage_failure(
        self,
        run_id: str,
        question: QuestionManipulation,
        error: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = metadata or {}

        entry = {
            "question_id": question.id,
            "question_number": str(question.question_number),
            "sequence_index": question.sequence_index,
            "source_identifier": question.source_identifier,
            "status": "failed",
            "job_id": metadata.get("job_id"),
            "error": error,
            "updated_at": isoformat(utc_now()),
        }

        self._persist_entry(run_id, question.id, entry)

    def mark_promoted(self, run_id: str, question_ids: Iterable[int]) -> None:
        with self._lock:
            data = self.load(run_id)
            updated = False
            for qid in question_ids:
                entry = data.get("questions", {}).get(str(qid))
                if not entry:
                    continue
                entry["status"] = "finalized"
                entry["finalized_at"] = isoformat(utc_now())
                updated = True
            if updated:
                self._write(run_id, data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _persist_entry(self, run_id: str, question_id: int, entry: Dict[str, Any]) -> None:
        with self._lock:
            data = self.load(run_id)
            data.setdefault("questions", {})[str(question_id)] = entry
            self._write(run_id, data)

    def _write(self, run_id: str, data: Dict[str, Any]) -> None:
        path = self._stage_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data["run_id"] = run_id
        data["updated_at"] = isoformat(utc_now())
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _stage_path(self, run_id: str) -> Path:
        return run_directory(run_id) / "mapping_generation_staged.json"

    def _extract_validation_summary(self, logs: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for log in logs:
            if log.get("status") == "success":
                result = log.get("validation_result")
                if isinstance(result, dict):
                    return result
        return None

