"""Background coordinator for GPT-5 mapping generation jobs."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from flask import current_app

from ...extensions import db
from ...models import QuestionManipulation
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from .gpt5_mapping_generator import GPT5MappingGeneratorService
from .mapping_generation_logger import get_mapping_logger


class MappingGenerationCoordinator:
    """Coordinate parallel mapping generation jobs."""

    def __init__(self, max_workers: int = 4) -> None:
        self.logger = get_logger(__name__)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._run_latest_job: Dict[str, str] = {}

    def submit_bulk_generation(self, run_id: str, *, k: int, strategy_name: str) -> str:
        """Submit a bulk generation job for every question in the run."""
        app = current_app._get_current_object()
        questions = (
            QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
            .order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
            .all()
        )

        question_snapshot = [
            {
                "id": question.id,
                "number": str(question.question_number),
                "sequence_index": question.sequence_index,
                "source_identifier": question.source_identifier,
            }
            for question in questions
        ]

        job_id = self._register_job(
            run_id=run_id,
            job_type="bulk",
            total=len(question_snapshot),
        )

        logger_service = get_mapping_logger()
        for question in question_snapshot:
            logger_service.log_generation(
                run_id=run_id,
                question_id=question["id"],
                question_number=question["number"],
                status="queued",
                details={"job_id": job_id},
                mappings_generated=0,
            )

        for question in question_snapshot:
            self._executor.submit(
                self._run_question_job,
                app,
                job_id,
                run_id,
                question["id"],
                question["number"],
                k,
                strategy_name,
            )

        if not question_snapshot:
            self._complete_job(job_id)

        return job_id

    def submit_question_generation(
        self,
        run_id: str,
        question_id: int,
        *,
        k: int,
        strategy_name: str,
    ) -> str:
        """Submit a mapping generation job for a single question."""
        app = current_app._get_current_object()
        question = QuestionManipulation.query.filter_by(
            pipeline_run_id=run_id,
            id=question_id,
        ).first()
        if not question:
            raise ValueError(f"Question {question_id} not found for run {run_id}")

        job_id = self._register_job(run_id=run_id, job_type="single", total=1)

        logger_service = get_mapping_logger()
        logger_service.log_generation(
            run_id=run_id,
            question_id=question.id,
            question_number=str(question.question_number),
            status="queued",
            details={"job_id": job_id},
            mappings_generated=0,
        )

        self._executor.submit(
            self._run_question_job,
            app,
            job_id,
            run_id,
            question.id,
            str(question.question_number),
            k,
            strategy_name,
        )

        return job_id

    def get_job_snapshot(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def get_latest_job_snapshot_for_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job_id = self._run_latest_job.get(run_id)
            if not job_id:
                return None
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_job(self, *, run_id: str, job_type: str, total: int) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            job_info = {
                "job_id": job_id,
                "run_id": run_id,
                "type": job_type,
                "status": "running" if total else "completed",
                "submitted_at": isoformat(utc_now()),
                "completed": 0,
                "errors": 0,
                "total": total,
            }
            self._jobs[job_id] = job_info
            self._run_latest_job[run_id] = job_id
        return job_id

    def _run_question_job(
        self,
        app,
        job_id: str,
        run_id: str,
        question_id: int,
        question_number: str,
        k: int,
        strategy_name: str,
    ) -> None:
        logger_service = get_mapping_logger()
        log_context = {"job_id": job_id}

        try:
            with app.app_context():
                logger_service.log_generation(
                    run_id=run_id,
                    question_id=question_id,
                    question_number=question_number,
                    status="running",
                    details=log_context,
                    mappings_generated=0,
                )

                service = GPT5MappingGeneratorService()
                final_result: Optional[Dict[str, Any]] = None
                try:
                    result = service.generate_mappings_for_question(
                        run_id=run_id,
                        question_id=question_id,
                        k=k,
                        strategy_name=strategy_name,
                        log_context=log_context,
                    )
                    final_result = result
                    if result and result.get("status") == "no_valid_mapping" and result.get("retry_hint"):
                        retry_context = {**log_context, "retry": True}
                        try:
                            retry_result = service.generate_mappings_for_question(
                                run_id=run_id,
                                question_id=question_id,
                                k=k,
                                strategy_name=strategy_name,
                                log_context=retry_context,
                                retry_hint=result.get("retry_hint"),
                            )
                            if retry_result:
                                final_result = retry_result
                        except Exception as retry_exc:  # pragma: no cover - defensive
                            logger_service.log_generation(
                                run_id=run_id,
                                question_id=question_id,
                                question_number=question_number,
                                status="failed",
                                details={**retry_context, "error": str(retry_exc)},
                                mappings_generated=0,
                            )
                            self.logger.warning(
                                "Retry mapping generation failed",
                                extra={
                                    "job_id": job_id,
                                    "run_id": run_id,
                                    "question_id": question_id,
                                    "error": str(retry_exc),
                                },
                            )
                            self._record_job_error(job_id)
                            final_result = final_result or result
                except Exception as exc:  # pragma: no cover - defensive
                    logger_service.log_generation(
                        run_id=run_id,
                        question_id=question_id,
                        question_number=question_number,
                        status="failed",
                        details={**log_context, "error": str(exc)},
                        mappings_generated=0,
                    )
                    self.logger.warning(
                        "Mapping generation failed",
                        extra={"job_id": job_id, "run_id": run_id, "question_id": question_id, "error": str(exc)},
                    )
                    self._record_job_error(job_id)
                else:
                    if (final_result or {}).get("status") == "no_valid_mapping":
                        logger_service.log_generation(
                            run_id=run_id,
                            question_id=question_id,
                            question_number=question_number,
                            status="no_valid_mapping",
                            details={
                                **log_context,
                                "mappings_generated": final_result.get("mappings_generated", 0),
                                "retry_hint": final_result.get("retry_hint"),
                            },
                            mappings_generated=final_result.get("mappings_generated", 0),
                        )
                finally:
                    db.session.remove()
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.exception(
                "Unexpected error running mapping job",
                extra={"job_id": job_id, "run_id": run_id, "question_id": question_id},
            )
            with app.app_context():  # attempt to log failure details
                logger_service.log_generation(
                    run_id=run_id,
                    question_id=question_id,
                    question_number=question_number,
                    status="failed",
                    details={**log_context, "error": str(exc)},
                    mappings_generated=0,
                )
            self._record_job_error(job_id)
        finally:
            self._increment_job_progress(job_id)

    def _increment_job_progress(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["completed"] += 1
            if job["completed"] >= job["total"]:
                self._complete_job_locked(job)

    def _record_job_error(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["errors"] += 1

    def _complete_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            self._complete_job_locked(job)

    def _complete_job_locked(self, job: Dict[str, Any]) -> None:
        if job["status"] == "completed":
            return
        job["status"] = "completed_with_errors" if job.get("errors") else "completed"
        job["completed_at"] = isoformat(utc_now())


_coordinator: Optional[MappingGenerationCoordinator] = None


def get_mapping_generation_coordinator() -> MappingGenerationCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = MappingGenerationCoordinator()
    return _coordinator

