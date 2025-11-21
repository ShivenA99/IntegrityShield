"""Streamlined mapping generation service with 3-set generation, sequential validation, and retry logic."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from threading import Lock

from flask import current_app

from ...extensions import db
from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.developer.live_logging_service import live_logging_service
from ...services.validation.gpt5_validation_service import GPT5ValidationService, ValidationResult
from ...utils.logging import get_logger
from ...utils.openai_responses import coerce_response_text
from ...utils.storage_paths import run_directory
from ...utils.time import isoformat, utc_now
from .gpt5_config import (
    GPT5_MODEL,
    GPT5_MAX_TOKENS,
    GPT5_REASONING_EFFORT,
    GPT5_GENERATION_REASONING_EFFORT,
    MAPPING_MAX_CONCURRENT,
    VALIDATION_MAX_CONCURRENT,
    API_TIMEOUT,
    MAX_RETRIES,
)
from .gpt5_mapping_generator import GPT5MappingGeneratorService
from .mapping_generation_logger import get_mapping_logger

try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    OpenAI = None  # type: ignore
    AsyncOpenAI = None  # type: ignore


# JSON Schema for mapping generation - supports multiple sets in one response
MAPPING_GENERATION_SCHEMA = {
    "name": "mappingBatch",
    "schema": {
        "type": "object",
        "properties": {
            "mapping_sets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "set_index": {"type": "integer"},
                        "target_option": {"type": ["string", "null"]},
                        "target_option_text": {"type": ["string", "null"]},
                        "signal_strategy": {"type": ["string", "null"]},
                        "mappings": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "original": {"type": "string"},
                                    "replacement": {"type": "string"},
                                    "start_pos": {"type": "integer"},
                                    "end_pos": {"type": "integer"},
                                    "context": {"type": "string"},
                                },
                                "required": ["original", "replacement"],
                                "additionalProperties": True,
                            },
                        },
                    },
                    "required": ["set_index", "mappings"],
                    "additionalProperties": True,
                },
            }
        },
        "required": ["mapping_sets"],
        "additionalProperties": True,
    },
}


@dataclass
class MappingSetStatus:
    """Status of a generated mapping set."""
    attempt: int
    set_index: int  # 1, 2, or 3
    target_option: Optional[str] = None
    signal_strategy: Optional[str] = None
    mappings_count: int = 0
    generated_at: str = field(default_factory=lambda: isoformat(utc_now()))


@dataclass
class ValidationOutcome:
    """Outcome of a validation attempt."""
    attempt: int
    set_index: int
    mapping_index: int
    is_valid: bool
    confidence: float
    deviation_score: float
    reasoning: str
    test_answer: str
    target_matched: Optional[bool] = None
    validated_at: str = field(default_factory=lambda: isoformat(utc_now()))


@dataclass
class QuestionGenerationStatus:
    """Status of generation for a single question."""
    question_id: int
    question_number: str
    status: str  # "pending" | "generating" | "validating" | "success" | "failed" | "retrying"
    retry_count: int = 0
    current_attempt: int = 1
    mapping_sets_generated: List[MappingSetStatus] = field(default_factory=list)
    validation_outcomes: List[ValidationOutcome] = field(default_factory=list)
    failure_rationales: List[str] = field(default_factory=list)
    generation_exceptions: List[Dict[str, Any]] = field(default_factory=list)
    valid_mapping: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: str = field(default_factory=lambda: isoformat(utc_now()))
    completed_at: Optional[str] = None


class StreamlinedMappingService:
    """Streamlined service for generating mappings with 3-set generation and sequential validation."""

    def __init__(self):
        self.logger = get_logger(__name__)
        self.structured_manager = StructuredDataManager()
        self.validator = GPT5ValidationService()
        self.generator = GPT5MappingGeneratorService()
        self.mapping_logger = get_mapping_logger()
        # In-memory status storage (keyed by run_id -> question_id)
        self._status_store: Dict[str, Dict[int, QuestionGenerationStatus]] = defaultdict(dict)
        # Semaphore to serialize database writes and prevent SQLite locks
        self._db_write_semaphore = asyncio.Semaphore(1)
        # Lock for file-based status persistence (thread-safe)
        self._status_file_lock = Lock()
        # Load persisted status on init
        self._load_persisted_statuses()

    async def generate_mappings_for_all_questions(
        self,
        run_id: str,
        max_concurrent: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate mappings for all questions with concurrency control.
        
        Args:
            run_id: Pipeline run ID
            max_concurrent: Maximum number of concurrent question generations (defaults to MAPPING_MAX_CONCURRENT)
            
        Returns:
            Dictionary with summary of results
        """
        if max_concurrent is None:
            max_concurrent = MAPPING_MAX_CONCURRENT
            
        questions = QuestionManipulation.query.filter_by(
            pipeline_run_id=run_id
        ).order_by(
            QuestionManipulation.sequence_index.asc(),
            QuestionManipulation.id.asc()
        ).all()

        if not questions:
            return {
                "run_id": run_id,
                "total_questions": 0,
                "success_count": 0,
                "failed_count": 0,
            }

        live_logging_service.emit(
            run_id,
            "smart_substitution",
            "INFO",
            f"Starting automatic mapping generation for {len(questions)} questions",
            component="mapping_generation",
            context={"total_questions": len(questions)},
        )

        semaphore = asyncio.Semaphore(max_concurrent)
        # Create tasks properly to ensure parallel execution with question tracking
        task_map = {}
        tasks = []
        for question in questions:
            task = asyncio.create_task(
                self._generate_for_question_with_semaphore(semaphore, run_id, question)
            )
            task_map[task] = question.id
            tasks.append(task)

        # Use as_completed for better progress tracking and UI updates
        # But ensure we wait for ALL tasks to complete before returning
        results = []
        completed_count = 0
        total_tasks = len(tasks)
        
        for completed_task in asyncio.as_completed(tasks):
            question_id = task_map.get(completed_task, None)
            try:
                result = await completed_task
                # Ensure question_id is in result for tracking
                if isinstance(result, dict) and "question_id" not in result and question_id:
                    result["question_id"] = question_id
                results.append(result)
                # Persist status after each question completes for real-time UI updates
                final_question_id = result.get("question_id") if isinstance(result, dict) else question_id
                if final_question_id:
                    status = self._status_store.get(run_id, {}).get(final_question_id)
                    if status:
                        self._persist_status(run_id, final_question_id, status)
                completed_count += 1
            except Exception as e:
                self.logger.error(
                    f"Error in parallel generation task for question {question_id}: {e}",
                    run_id=run_id,
                    question_id=question_id,
                    exc_info=True
                )
                results.append({"status": "error", "error": str(e), "question_id": question_id})
                completed_count += 1
        
        # Ensure all tasks are awaited (defensive check)
        if completed_count < total_tasks:
            self.logger.warning(
                f"Not all tasks completed: {completed_count}/{total_tasks}",
                run_id=run_id
            )
            # Wait for any remaining tasks
            remaining_tasks = [t for t in tasks if not t.done()]
            if remaining_tasks:
                await asyncio.gather(*remaining_tasks, return_exceptions=True)

        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
        failed_count = len(results) - success_count

        live_logging_service.emit(
            run_id,
            "smart_substitution",
            "INFO",
            f"Completed mapping generation: {success_count} succeeded, {failed_count} failed",
            component="mapping_generation",
            context={
                "total_questions": len(questions),
                "success_count": success_count,
                "failed_count": failed_count,
            },
        )

        return {
            "run_id": run_id,
            "total_questions": len(questions),
            "success_count": success_count,
            "failed_count": failed_count,
        }

    async def generate_mappings_for_single_question(
        self,
        run_id: str,
        question_id: int,
    ) -> Dict[str, Any]:
        """
        Generate mappings for a single question.
        
        Args:
            run_id: Pipeline run ID
            question_id: Question ID
            
        Returns:
            Dictionary with generation result
        """
        question = QuestionManipulation.query.filter_by(
            pipeline_run_id=run_id,
            id=question_id
        ).first()

        if not question:
            raise ValueError(f"Question {question_id} not found for run {run_id}")

        return await self._generate_for_question(run_id, question)

    async def _generate_for_question_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        run_id: str,
        question: QuestionManipulation,
    ) -> Dict[str, Any]:
        """Generate mappings with semaphore for concurrency control."""
        async with semaphore:
            return await self._generate_for_question(run_id, question)

    async def _generate_for_question(
        self,
        run_id: str,
        question: QuestionManipulation,
    ) -> Dict[str, Any]:
        """
        Generate mappings for a single question with retry logic.
        
        Returns:
            Dictionary with status and result
        """
        question_id = question.id
        question_number = question.question_number

        # Initialize status
        status = QuestionGenerationStatus(
            question_id=question_id,
            question_number=question_number,
            status="generating",
        )
        self._status_store[run_id][question_id] = status
        self._persist_status(run_id, question_id, status)

        # Log generation start
        self.mapping_logger.log_generation(
            run_id=run_id,
            question_id=question_id,
            question_number=question_number,
            status="pending",
            details={
                "attempt": 1,
                "question_id": question_id,
                "question_number": question_number,
            },
            mappings_generated=0,
        )

        # Emit start log
        live_logging_service.emit(
            run_id,
            "smart_substitution",
            "INFO",
            f"Starting mapping generation for question {question_number}",
            component="mapping_generation",
            context={
                "question_id": question_id,
                "question_number": question_number,
                "attempt": 1,
            },
        )

        try:
            # Load structured data
            self.logger.info(
                f"Loading structured data for question {question_number}",
                run_id=run_id,
                question_id=question_id,
            )
            structured = self.structured_manager.load(run_id)
            if not structured:
                error_msg = f"Structured data not found for run {run_id}"
                self.logger.error(error_msg, run_id=run_id, question_id=question_id)
                raise ValueError(error_msg)

            # Get question data
            question_data = self.generator._get_question_data(run_id, question, structured)
            question_data = self.generator._normalize_dict_keys(question_data)

            # Get LaTeX stem text
            self.logger.debug(
                f"Extracting LaTeX stem text for question {question_number}",
                run_id=run_id,
                question_id=question_id,
            )
            latex_stem_text = self.generator._extract_latex_stem_text(run_id, question, structured)
            if not latex_stem_text:
                error_msg = f"Could not extract LaTeX stem text for question {question_id}"
                self.logger.error(error_msg, run_id=run_id, question_id=question_id)
                raise ValueError(error_msg)
            question_data["latex_stem_text"] = latex_stem_text

            question_type = question_data.get("question_type", "mcq_single")
            gold_answer = question_data.get("gold_answer", "")
            options = question_data.get("options", {})

            self.logger.info(
                f"Question data loaded: type={question_type}, gold_answer={gold_answer}, options_count={len(options)}",
                run_id=run_id,
                question_id=question_id,
                question_type=question_type,
            )

            # Determine target options or signal strategies
            target_configs = self._determine_target_configs(question_data, question_type)
            self.logger.info(
                f"Determined {len(target_configs)} target configs for question {question_number}",
                run_id=run_id,
                question_id=question_id,
                target_configs=[{"target_option": c.get("target_option"), "signal_strategy": c.get("signal_strategy")} for c in target_configs],
            )

            # First attempt: Generate 3 sets
            attempt = 1
            max_attempts = 2  # Initial attempt + 1 retry

            while attempt <= max_attempts:
                status.current_attempt = attempt
                if attempt > 1:
                    status.status = "retrying"
                    status.retry_count = attempt - 1
                    live_logging_service.emit(
                        run_id,
                        "smart_substitution",
                        "INFO",
                        f"Retrying mapping generation for question {question_number} (Attempt {attempt})",
                        component="mapping_generation",
                        context={
                            "question_id": question_id,
                            "question_number": question_number,
                            "attempt": attempt,
                            "failure_rationales": status.failure_rationales,
                        },
                    )

                # Generate all 3 mapping sets in ONE call
                status.status = "generating"
                self._persist_status(run_id, question_id, status)
                self.logger.info(
                    f"Status transition: generating all sets (attempt {attempt})",
                    run_id=run_id,
                    question_id=question_id,
                    attempt=attempt,
                )
                
                try:
                    # Single call to generate all sets
                    all_sets = await self._generate_all_mapping_sets(
                        run_id=run_id,
                        question_id=question_id,
                        question_number=question_number,
                        question_data=question_data,
                        target_configs=target_configs,
                        attempt=attempt,
                        failure_rationales=status.failure_rationales if attempt > 1 else None,
                    )
                    
                    mapping_sets = []
                    total_mappings_generated = 0
                    
                    # Process each set from the response
                    for set_data in all_sets:
                        set_idx = set_data["set_index"]
                        mappings = set_data["mappings"]
                        target_config = set_data["target_config"]
                        
                        set_status = MappingSetStatus(
                            attempt=attempt,
                            set_index=set_idx,
                            target_option=target_config.get("target_option"),
                            signal_strategy=target_config.get("signal_strategy"),
                            mappings_count=len(mappings),
                        )
                        status.mapping_sets_generated.append(set_status)
                        mapping_sets.append((set_idx, mappings, target_config))
                        total_mappings_generated += len(mappings)

                        # Update generation log with mappings count
                        self.mapping_logger.log_generation(
                            run_id=run_id,
                            question_id=question_id,
                            question_number=question_number,
                            status="success",
                            details={
                                "attempt": attempt,
                                "set_index": set_idx,
                                "target_option": target_config.get("target_option"),
                                "signal_strategy": target_config.get("signal_strategy"),
                                "mappings_count": len(mappings),
                                "total_mappings": total_mappings_generated,
                            },
                            mappings_generated=total_mappings_generated,
                        )

                        live_logging_service.emit(
                            run_id,
                            "smart_substitution",
                            "INFO",
                            f"Generated mapping set {set_idx} for question {question_number}",
                            component="mapping_generation",
                            context={
                                "question_id": question_id,
                                "question_number": question_number,
                                "attempt": attempt,
                                "set_index": set_idx,
                                "target_option": target_config.get("target_option"),
                                "signal_strategy": target_config.get("signal_strategy"),
                                "mappings_count": len(mappings),
                            },
                        )

                except Exception as e:
                    import traceback
                    exception_dict = {
                        "set_index": None,  # All sets failed in one call
                        "attempt": attempt,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "traceback": traceback.format_exc(),
                    }
                    status.generation_exceptions.append(exception_dict)
                    self._persist_status(run_id, question_id, status)
                    
                    self.logger.error(
                        f"Failed to generate all mapping sets for question {question_id}: {e}",
                        run_id=run_id,
                        question_id=question_id,
                        attempt=attempt,
                        error_type=type(e).__name__,
                        exc_info=True,
                    )
                    # Update generation log with failure
                    self.mapping_logger.log_generation(
                        run_id=run_id,
                        question_id=question_id,
                        question_number=question_number,
                        status="failed",
                        details={
                            "attempt": attempt,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                        mappings_generated=0,
                    )
                    # Continue to next attempt or fail
                    mapping_sets = []
                    total_mappings_generated = 0

                # Check if any mappings were generated
                if not mapping_sets:
                    # All generation attempts failed
                    error_types = {}
                    for exc in status.generation_exceptions:
                        error_type = exc.get("error_type", "Unknown")
                        error_types[error_type] = error_types.get(error_type, 0) + 1
                    
                    error_summary = ", ".join([f"{count}x {err_type}" for err_type, count in error_types.items()])
                    unique_errors = list(set([exc.get("error", "Unknown error") for exc in status.generation_exceptions]))
                    
                    status.status = "failed"
                    status.error = f"Failed to generate any mapping sets. All {len(status.generation_exceptions)} generation attempts raised exceptions. Error types: {error_summary}. Errors: {'; '.join(unique_errors[:3])}"
                    
                    # Add generation exceptions to failure_rationales
                    for exc in status.generation_exceptions:
                        rationale = f"Generation Set {exc['set_index']} (Attempt {exc['attempt']}): {exc['error_type']}: {exc['error']}"
                        if rationale not in status.failure_rationales:
                            status.failure_rationales.append(rationale)
                    
                    status.completed_at = isoformat(utc_now())
                    self._persist_status(run_id, question_id, status)
                    
                    self.logger.error(
                        f"All mapping generation attempts failed for question {question_number}",
                        run_id=run_id,
                        question_id=question_id,
                        attempt=attempt,
                        total_exceptions=len(status.generation_exceptions),
                        error_types=error_types,
                        unique_errors=unique_errors,
                    )
                    
                    # Update generation log with final failure
                    self.mapping_logger.log_generation(
                        run_id=run_id,
                        question_id=question_id,
                        question_number=question_number,
                        status="failed",
                        details={
                            "total_attempts": attempt,
                            "mappings_validated": 0,
                            "error": status.error,
                            "failure_rationales": status.failure_rationales,
                            "generation_exceptions_count": len(status.generation_exceptions),
                        },
                        mappings_generated=total_mappings_generated,
                    )
                    
                    live_logging_service.emit(
                        run_id,
                        "smart_substitution",
                        "ERROR",
                        f"Failed to generate any mapping sets for question {question_number} after {attempt} attempt(s)",
                        component="mapping_generation",
                        context={
                            "question_id": question_id,
                            "question_number": question_number,
                            "total_attempts": attempt,
                            "error": status.error,
                            "generation_exceptions_count": len(status.generation_exceptions),
                        },
                    )
                    
                    # If we haven't exhausted retries, continue to retry
                    if attempt < max_attempts:
                        attempt += 1
                        continue
                    else:
                        return {
                            "status": "failed",
                            "question_id": question_id,
                            "question_number": question_number,
                            "error": status.error,
                            "failure_rationales": status.failure_rationales,
                            "generation_exceptions": status.generation_exceptions,
                            "total_attempts": max_attempts,
                        }

                # Validate in parallel (all mappings in a set concurrently) until first valid found
                status.status = "validating"
                self._persist_status(run_id, question_id, status)
                self.logger.info(
                    f"Status transition: validating (attempt {attempt}, {len(mapping_sets)} sets to validate)",
                    run_id=run_id,
                    question_id=question_id,
                    attempt=attempt,
                    sets_count=len(mapping_sets),
                )
                valid_mapping = None
                mappings_validated_count = 0
                
                # Semaphore to limit concurrent validation calls
                validation_semaphore = asyncio.Semaphore(VALIDATION_MAX_CONCURRENT)

                for set_idx, mappings, target_config in mapping_sets:
                    # Validate all mappings in this set in parallel
                    validation_tasks = []
                    task_data = []
                    for mapping_idx, mapping in enumerate(mappings):
                        task = asyncio.create_task(
                            self._validate_mapping_set_with_semaphore(
                                validation_semaphore,
                                run_id=run_id,
                                question_id=question_id,
                                question_number=question_number,
                                question_data=question_data,
                                mapping=mapping,
                                set_index=set_idx,
                                mapping_index=mapping_idx,
                                attempt=attempt,
                                target_config=target_config,
                            )
                        )
                        validation_tasks.append(task)
                        task_data.append((mapping_idx, mapping))
                    
                    # Wait for all validations in this set to complete in parallel with timeout
                    # Use 2x API_TIMEOUT to allow for parallel execution of multiple validations
                    try:
                        validation_results = await asyncio.wait_for(
                            asyncio.gather(*validation_tasks, return_exceptions=True),
                            timeout=API_TIMEOUT * 2,  # Allow 2x timeout for parallel validations
                        )
                    except asyncio.TimeoutError:
                        self.logger.error(
                            f"Validation batch timed out after {API_TIMEOUT * 2}s",
                            run_id=run_id,
                            question_id=question_id,
                            set_index=set_idx,
                            attempt=attempt,
                            tasks_count=len(validation_tasks),
                        )
                        # Collect results from completed tasks and mark pending ones as timed out
                        validation_results = []
                        for task in validation_tasks:
                            if task.done():
                                try:
                                    validation_results.append(task.result())
                                except Exception as e:
                                    validation_results.append(e)
                            else:
                                # Task is still pending - mark as timed out
                                # Use a regular Exception that will be handled by the exception handler below
                                validation_results.append(
                                    TimeoutError(f"Validation task timed out after {API_TIMEOUT * 2}s")
                                )
                                # Cancel the task to free resources
                                task.cancel()
                    
                    for (mapping_idx, mapping), validation_result in zip(task_data, validation_results):
                        mappings_validated_count += 1
                        
                        # Handle exceptions from validation
                        if isinstance(validation_result, Exception):
                            error_type = type(validation_result).__name__
                            error_msg = str(validation_result)
                            self.logger.error(
                                f"Validation exception for mapping {mapping_idx}: {error_type}: {error_msg}",
                                run_id=run_id,
                                question_id=question_id,
                                set_index=set_idx,
                                mapping_index=mapping_idx,
                                attempt=attempt,
                                error_type=error_type,
                                exc_info=True,
                            )
                            # Create a failed validation result
                            validation_result = ValidationResult(
                                is_valid=False,
                                confidence=0.0,
                                deviation_score=0.0,
                                reasoning=f"Validation error: {error_msg}",
                                semantic_similarity=0.0,
                                factual_accuracy=False,
                                question_type_specific_notes=f"Validation exception: {error_type}",
                                gold_answer=question_data.get("gold_answer", ""),
                                test_answer="",
                                model_used="none"
                            )

                        outcome = ValidationOutcome(
                            attempt=attempt,
                            set_index=set_idx,
                            mapping_index=mapping_idx,
                            is_valid=validation_result.is_valid,
                            confidence=validation_result.confidence,
                            deviation_score=validation_result.deviation_score,
                            reasoning=validation_result.reasoning,
                            test_answer=validation_result.test_answer,
                            target_matched=validation_result.target_matched,
                        )
                        status.validation_outcomes.append(outcome)
                        self._persist_status(run_id, question_id, status)

                        # Log validation event
                        self.mapping_logger.log_validation(
                            run_id=run_id,
                            question_id=question_id,
                            question_number=question_number,
                            mapping_index=mapping_idx,
                            status="success" if validation_result.is_valid else "failed",
                            details={
                                "validation_result": {
                                    "is_valid": validation_result.is_valid,
                                    "confidence": validation_result.confidence,
                                    "deviation_score": validation_result.deviation_score,
                                    "reasoning": validation_result.reasoning,
                                    "test_answer": validation_result.test_answer,
                                    "target_matched": validation_result.target_matched,
                                },
                                "set_index": set_idx,
                                "attempt": attempt,
                                "mapping_preview": {
                                    "original": mapping.get("original", "")[:50] + "..." if len(mapping.get("original", "")) > 50 else mapping.get("original", ""),
                                    "replacement": mapping.get("replacement", "")[:50] + "..." if len(mapping.get("replacement", "")) > 50 else mapping.get("replacement", ""),
                                },
                            },
                        )

                        live_logging_service.emit(
                            run_id,
                            "smart_substitution",
                            "INFO" if validation_result.is_valid else "WARNING",
                            f"Validation result for question {question_number}, Set {set_idx}, Mapping {mapping_idx + 1}: {'Valid' if validation_result.is_valid else 'Invalid'}",
                            component="mapping_generation",
                            context={
                                "question_id": question_id,
                                "question_number": question_number,
                                "attempt": attempt,
                                "set_index": set_idx,
                                "mapping_index": mapping_idx,
                                "is_valid": validation_result.is_valid,
                                "confidence": validation_result.confidence,
                                "deviation_score": validation_result.deviation_score,
                                "reasoning": validation_result.reasoning,
                            },
                        )

                        if validation_result.is_valid and not valid_mapping:
                            valid_mapping = mapping
                            # Enrich mapping with validation metadata
                            valid_mapping["validated"] = True
                            valid_mapping["confidence"] = validation_result.confidence
                            valid_mapping["deviation_score"] = validation_result.deviation_score
                            valid_mapping["validation_reasoning"] = validation_result.reasoning
                            if validation_result.target_matched is not None:
                                valid_mapping["target_matched"] = validation_result.target_matched

                    if valid_mapping:
                        break

                # If valid mapping found, save and return
                if valid_mapping:
                    status.status = "success"
                    status.valid_mapping = valid_mapping
                    status.completed_at = isoformat(utc_now())
                    self._persist_status(run_id, question_id, status)
                    
                    self.logger.info(
                        f"Status transition: success (attempt {attempt}, found valid mapping)",
                        run_id=run_id,
                        question_id=question_id,
                        attempt=attempt,
                    )

                    # Update generation log with final success
                    self.mapping_logger.log_generation(
                        run_id=run_id,
                        question_id=question_id,
                        question_number=question_number,
                        status="success",
                        details={
                            "attempt": attempt,
                            "total_attempts": attempt,
                            "mappings_validated": mappings_validated_count,
                            "valid_mapping_preview": {
                                "original": valid_mapping.get("original", "")[:50] + "..." if len(valid_mapping.get("original", "")) > 50 else valid_mapping.get("original", ""),
                                "replacement": valid_mapping.get("replacement", "")[:50] + "..." if len(valid_mapping.get("replacement", "")) > 50 else valid_mapping.get("replacement", ""),
                            },
                        },
                        mappings_generated=total_mappings_generated,
                    )

                    await self._save_valid_mapping(run_id, question, valid_mapping)

                    live_logging_service.emit(
                        run_id,
                        "smart_substitution",
                        "INFO",
                        f"Successfully generated and validated mapping for question {question_number}",
                        component="mapping_generation",
                        context={
                            "question_id": question_id,
                            "question_number": question_number,
                            "attempt": attempt,
                            "total_attempts": attempt,
                        },
                    )

                    return {
                        "status": "success",
                        "question_id": question_id,
                        "question_number": question_number,
                        "valid_mapping": valid_mapping,
                        "total_attempts": attempt,
                    }

                # Collect failure rationales from validation outcomes
                for outcome in status.validation_outcomes:
                    if not outcome.is_valid and outcome.reasoning:
                        rationale = f"Set {outcome.set_index}, Mapping {outcome.mapping_index + 1}: {outcome.reasoning}"
                        if rationale not in status.failure_rationales:
                            status.failure_rationales.append(rationale)

                # If all sets failed and we haven't exhausted retries, retry
                if attempt < max_attempts:
                    self.logger.info(
                        f"Status transition: retrying (attempt {attempt} failed, moving to attempt {attempt + 1})",
                        run_id=run_id,
                        question_id=question_id,
                        attempt=attempt,
                        failure_rationales=status.failure_rationales,
                    )
                    attempt += 1
                    continue
                else:
                    # All attempts exhausted - all validations failed
                    status.status = "failed"
                    status.error = f"All {len(mapping_sets)} mapping sets failed validation after {max_attempts} attempt(s). {len(status.validation_outcomes)} validation(s) attempted, all invalid."
                    status.completed_at = isoformat(utc_now())
                    self._persist_status(run_id, question_id, status)
                    
                    self.logger.error(
                        f"Status transition: failed (all {max_attempts} attempts exhausted)",
                        run_id=run_id,
                        question_id=question_id,
                        total_attempts=max_attempts,
                        failure_rationales=status.failure_rationales,
                    )

                    # Update generation log with final failure
                    self.mapping_logger.log_generation(
                        run_id=run_id,
                        question_id=question_id,
                        question_number=question_number,
                        status="failed",
                        details={
                            "total_attempts": max_attempts,
                            "mappings_validated": mappings_validated_count,
                            "error": status.error,
                            "failure_rationales": status.failure_rationales,
                        },
                        mappings_generated=total_mappings_generated,
                    )

                    live_logging_service.emit(
                        run_id,
                        "smart_substitution",
                        "ERROR",
                        f"Failed to generate valid mapping for question {question_number} after {max_attempts} attempts",
                        component="mapping_generation",
                        context={
                            "question_id": question_id,
                            "question_number": question_number,
                            "total_attempts": max_attempts,
                            "failure_rationales": status.failure_rationales,
                        },
                    )

                    return {
                        "status": "failed",
                        "question_id": question_id,
                        "question_number": question_number,
                        "error": status.error,
                        "failure_rationales": status.failure_rationales,
                        "total_attempts": max_attempts,
                    }

        except Exception as e:
            status.status = "failed"
            status.error = str(e)
            status.completed_at = isoformat(utc_now())
            self._persist_status(run_id, question_id, status)
            
            self.logger.error(
                f"Status transition: failed (exception occurred)",
                run_id=run_id,
                question_id=question_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

            # Update generation log with exception failure
            self.mapping_logger.log_generation(
                run_id=run_id,
                question_id=question_id,
                question_number=question_number,
                status="failed",
                details={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "exception_occurred": True,
                },
                mappings_generated=0,
            )

            live_logging_service.emit(
                run_id,
                "smart_substitution",
                "ERROR",
                f"Error generating mappings for question {question_number}: {str(e)}",
                component="mapping_generation",
                context={
                    "question_id": question_id,
                    "question_number": question_number,
                    "error": str(e),
                },
            )

            return {
                "status": "failed",
                "question_id": question_id,
                "question_number": question_number,
                "error": str(e),
            }

    def _determine_target_configs(
        self,
        question_data: Dict[str, Any],
        question_type: str,
    ) -> List[Dict[str, Any]]:
        """
        Determine target configurations for 3 mapping sets.
        
        For MCQ: target different wrong options (up to 3)
        For signal types: use different signal strategies
        """
        configs = []

        if question_type in ["mcq_single", "mcq_multi", "true_false", "matching"]:
            # Target-based: get wrong options
            options = question_data.get("options", {})
            gold_answer = question_data.get("gold_answer", "")
            
            # Extract gold answer label (e.g., "B" from "B" or "B. Temperature")
            gold_label = self._extract_label_from_string(gold_answer)
            
            # Get all option labels
            option_labels = [k for k in options.keys() if k != gold_label]
            
            # Select up to 3 wrong options
            for label in option_labels[:3]:
                option_text = options.get(label, "")
                configs.append({
                    "target_option": label,
                    "target_option_text": option_text,
                    "signal_strategy": None,
                })
            
            # If we have fewer than 3 options, pad with None
            while len(configs) < 3:
                configs.append({
                    "target_option": None,
                    "target_option_text": None,
                    "signal_strategy": None,
                })

        else:
            # Signal-based: use different signal strategies
            signal_strategies = [
                "opposite_meaning",
                "negation",
                "context_shift",
            ]
            
            for strategy in signal_strategies[:3]:
                configs.append({
                    "target_option": None,
                    "target_option_text": None,
                    "signal_strategy": strategy,
                })

        return configs[:3]  # Ensure exactly 3

    def _extract_label_from_string(self, text: str) -> str:
        """Extract single-letter label from string like 'B. Temperature' or 'B)'."""
        if not text:
            return ""
        
        # Try to extract single letter at start
        match = re.match(r"^([A-Z])[\.\)\s]", text.strip())
        if match:
            return match.group(1)
        
        # If it's just a single letter
        if len(text.strip()) == 1 and text.strip().isalpha():
            return text.strip().upper()
        
        return text.strip()

    async def _generate_all_mapping_sets(
        self,
        run_id: str,
        question_id: int,
        question_number: str,
        question_data: Dict[str, Any],
        target_configs: List[Dict[str, Any]],
        attempt: int,
        failure_rationales: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate all mapping sets in ONE call using GPT-5.1 Responses API.
        
        Returns list of dicts with keys: set_index, mappings, target_config
        """
        prompt = self._build_generation_prompt_all_sets(
            question_data=question_data,
            target_configs=target_configs,
            failure_rationales=failure_rationales,
        )

        # Log before API call
        prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
        self.logger.debug(
            f"Generating all mapping sets in one call (attempt {attempt})",
            run_id=run_id,
            question_id=question_id,
            attempt=attempt,
            sets_count=len(target_configs),
            prompt_preview=prompt_preview,
            failure_rationales_count=len(failure_rationales) if failure_rationales else 0,
        )

        api_key = os.getenv("OPENAI_API_KEY") or current_app.config.get("OPENAI_API_KEY")
        if not api_key or not AsyncOpenAI:
            error_msg = "OpenAI API key not configured or AsyncOpenAI not available"
            self.logger.error(error_msg, run_id=run_id, question_id=question_id)
            raise RuntimeError(error_msg)

        client = AsyncOpenAI(api_key=api_key, timeout=API_TIMEOUT)

        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are an expert at generating text substitutions for academic questions. "
                            "Your goal is to create subtle but effective text changes that will cause "
                            "an LLM to answer incorrectly. Return strict JSON following the required schema."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ]

        try:
            # Use AsyncOpenAI directly for native async performance
            # NOTE: GPT-5.1 Responses API may not support response_format with json_schema
            # Instead, we rely on explicit prompt instructions and few-shot examples
            response = await client.responses.create(
                model=GPT5_MODEL,
                input=messages,
                reasoning={"effort": GPT5_GENERATION_REASONING_EFFORT},
                max_output_tokens=GPT5_MAX_TOKENS,
                metadata={"task": "mapping_generation", "run_id": run_id, "question_id": str(question_id)},
            )

            # Extract response content with better error handling
            content = coerce_response_text(response)
            if not content or not content.strip():
                # Log response metadata for debugging
                response_id = getattr(response, "id", None)
                response_model = getattr(response, "model", None)
                self.logger.error(
                    f"Empty response from GPT-5.1 Responses API",
                    run_id=run_id,
                    question_id=question_id,
                    attempt=attempt,
                    response_id=response_id,
                    response_model=response_model,
                )
                raise ValueError("Empty response from GPT-5.1 Responses API")

            # Parse JSON response with comprehensive error handling and recovery
            parsed = None
            content_original = content
            
            # Strategy 1: Try direct JSON parsing
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as json_err:
                self.logger.warning(
                    f"Direct JSON parse failed, attempting recovery: {json_err}",
                    run_id=run_id,
                    question_id=question_id,
                    attempt=attempt,
                    error_pos=json_err.pos if hasattr(json_err, 'pos') else None,
                )
                
                # Strategy 2: Extract from markdown code blocks
                for marker in ["```json", "```"]:
                    if marker in content:
                        try:
                            json_start = content.find(marker) + len(marker)
                            json_end = content.find("```", json_start)
                            if json_end > json_start:
                                extracted = content[json_start:json_end].strip()
                                parsed = json.loads(extracted)
                                self.logger.info(
                                    f"Successfully extracted JSON from {marker} code block",
                                    run_id=run_id,
                                    question_id=question_id,
                                )
                                break
                        except (json.JSONDecodeError, ValueError):
                            continue
                
                # Strategy 3: Try to find JSON object boundaries
                if parsed is None:
                    try:
                        # Find first { and last }
                        first_brace = content.find("{")
                        last_brace = content.rfind("}")
                        if first_brace >= 0 and last_brace > first_brace:
                            extracted = content[first_brace:last_brace + 1]
                            parsed = json.loads(extracted)
                            self.logger.info(
                                f"Successfully extracted JSON by finding brace boundaries",
                                run_id=run_id,
                                question_id=question_id,
                            )
                    except (json.JSONDecodeError, ValueError):
                        pass
                
                # Strategy 4: Try to fix common JSON issues
                if parsed is None:
                    try:
                        # Remove leading/trailing whitespace and non-JSON text
                        cleaned = content.strip()
                        # Remove text before first {
                        first_brace = cleaned.find("{")
                        if first_brace > 0:
                            cleaned = cleaned[first_brace:]
                        # Remove text after last }
                        last_brace = cleaned.rfind("}")
                        if last_brace >= 0:
                            cleaned = cleaned[:last_brace + 1]
                        
                        # Try to fix unterminated strings (common issue)
                        # This is a heuristic - count quotes and try to balance
                        quote_count = cleaned.count('"')
                        if quote_count % 2 != 0:
                            # Odd number of quotes - might be unterminated string
                            # Try adding a closing quote before the last }
                            last_quote_pos = cleaned.rfind('"')
                            if last_quote_pos > 0 and last_quote_pos < len(cleaned) - 2:
                                # Check if it's likely an unterminated string
                                before_quote = cleaned[last_quote_pos - 1] if last_quote_pos > 0 else ''
                                after_quote = cleaned[last_quote_pos + 1] if last_quote_pos + 1 < len(cleaned) else ''
                                if before_quote != '\\' and after_quote not in ['"', ',', '}', ']', ':', ' ']:
                                    # Might need to close the string
                                    cleaned = cleaned[:last_quote_pos + 1] + '"' + cleaned[last_quote_pos + 1:]
                        
                        parsed = json.loads(cleaned)
                        self.logger.info(
                            f"Successfully parsed JSON after cleaning",
                            run_id=run_id,
                            question_id=question_id,
                        )
                    except (json.JSONDecodeError, ValueError) as e:
                        # All recovery strategies failed
                        content_preview = content[:500] + "..." if len(content) > 500 else content
                        response_id = getattr(response, "id", None)
                        response_model = getattr(response, "model", None)
                        self.logger.error(
                            f"All JSON parsing recovery strategies failed: {json_err}",
                            run_id=run_id,
                            question_id=question_id,
                            attempt=attempt,
                            original_error=str(json_err),
                            recovery_error=str(e),
                            content_preview=content_preview,
                            content_length=len(content),
                            response_id=response_id,
                            response_model=response_model,
                        )
                        raise json_err
            
            if parsed is None:
                raise ValueError("Failed to parse JSON response after all recovery attempts")

            # Validate response structure
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
            
            mapping_sets_data = parsed.get("mapping_sets", [])

            if not mapping_sets_data:
                response_id = getattr(response, "id", None)
                self.logger.warning(
                    f"No mapping_sets found in response",
                    run_id=run_id,
                    question_id=question_id,
                    attempt=attempt,
                    response_id=response_id,
                    parsed_keys=list(parsed.keys()) if isinstance(parsed, dict) else None,
                )
                raise ValueError("No mapping_sets found in response")

            # Process each set and match with target_configs
            result_sets = []
            for set_data in mapping_sets_data:
                set_idx = set_data.get("set_index")
                if set_idx is None or set_idx < 1 or set_idx > len(target_configs):
                    self.logger.warning(
                        f"Invalid set_index {set_idx} in response, skipping",
                        run_id=run_id,
                        question_id=question_id,
                    )
                    continue
                
                target_config = target_configs[set_idx - 1]  # Convert to 0-based index
                mappings = set_data.get("mappings", [])

                # Add metadata to each mapping and validate length constraint
                valid_mappings = []
                for mapping in mappings:
                    original = mapping.get("original", "")
                    replacement = mapping.get("replacement", "")
                    
                    # Validate length constraint: replacement must be <= original length
                    if len(replacement) > len(original):
                        self.logger.warning(
                            f"Mapping rejected: replacement length ({len(replacement)}) > original length ({len(original)})",
                            run_id=run_id,
                            question_id=question_id,
                            set_index=set_idx,
                            original_preview=original[:50],
                            replacement_preview=replacement[:50],
                        )
                        continue  # Skip this mapping
                    
                    mapping["latex_stem_text"] = question_data.get("latex_stem_text", "")
                    mapping["question_index"] = question_number
                    if target_config.get("target_option"):
                        mapping["target_option"] = target_config["target_option"]
                        mapping["target_option_text"] = target_config.get("target_option_text")
                    if target_config.get("signal_strategy"):
                        mapping["signal_strategy"] = target_config["signal_strategy"]
                    
                    valid_mappings.append(mapping)
                
                # Use only valid mappings
                mappings = valid_mappings
                
                # Warn if all mappings in a set were rejected
                if not mappings and set_data.get("mappings"):
                    self.logger.warning(
                        f"All mappings in set {set_idx} were rejected due to length constraint violations",
                        run_id=run_id,
                        question_id=question_id,
                        set_index=set_idx,
                        original_mappings_count=len(set_data.get("mappings", [])),
                    )

                result_sets.append({
                    "set_index": set_idx,
                    "mappings": mappings,
                    "target_config": target_config,
                })

            if not result_sets:
                raise ValueError("No valid mapping sets found in response")

            return result_sets

        except Exception as e:
            self.logger.error(
                f"Failed to generate all mapping sets: {e}",
                run_id=run_id,
                question_id=question_id,
                exc_info=True,
            )
            raise

    def _build_generation_prompt_all_sets(
        self,
        question_data: Dict[str, Any],
        target_configs: List[Dict[str, Any]],
        failure_rationales: Optional[List[str]] = None,
    ) -> str:
        """Build generation prompt to generate ALL sets in one call."""
        question_type = question_data.get("question_type", "mcq_single")
        stem_text = question_data.get("stem_text", "")
        gold_answer = question_data.get("gold_answer", "")
        options = question_data.get("options", {})

        prompt = f"""Generate text substitution mappings for the following question. You must generate {len(target_configs)} DIFFERENT sets of mappings, each targeting a different outcome.

QUESTION TYPE: {question_type}
QUESTION TEXT: {stem_text}
GOLD ANSWER: {gold_answer}
"""

        if options:
            prompt += "\nOPTIONS:\n"
            for key, value in options.items():
                prompt += f"{key}. {value}\n"

        # Add all target configurations
        prompt += f"\nGENERATE {len(target_configs)} MAPPING SETS:\n"
        for idx, target_config in enumerate(target_configs, start=1):
            if target_config.get("target_option"):
                prompt += f"\nSET {idx}: Target option {target_config['target_option']} ({target_config.get('target_option_text', '')})\n"
                prompt += f"   - Generate EXACTLY ONE mapping that will cause the LLM to select option {target_config['target_option']} instead of the gold answer.\n"
                prompt += f"   - The mapping can be a single word (best case) or the entire question stem substring (worst case).\n"
            elif target_config.get("signal_strategy"):
                prompt += f"\nSET {idx}: Signal strategy '{target_config['signal_strategy']}'\n"
                prompt += f"   - Generate EXACTLY ONE mapping using the '{target_config['signal_strategy']}' strategy to create subtle but effective changes.\n"
                prompt += f"   - The mapping can be a single word (best case) or the entire question stem substring (worst case).\n"
            else:
                prompt += f"\nSET {idx}: General manipulation\n"
                prompt += f"   - Generate EXACTLY ONE mapping that will cause the LLM to answer incorrectly.\n"
                prompt += f"   - The mapping can be a single word (best case) or the entire question stem substring (worst case).\n"
        
        prompt += "\n\nMAPPING CONSTRAINTS:\n"
        prompt += "- Each mapping must replace a contiguous substring from the question text\n"
        prompt += "- CRITICAL: The replacement substring MUST be DIFFERENT from the original substring. Do NOT generate mappings where original == replacement (e.g., \"power\" → \"power\" is INVALID). The replacement MUST change the text to create actual manipulation.\n"
        prompt += "- CRITICAL: Neither original nor replacement can be empty strings. Both must contain actual text.\n"
        prompt += "- The replacement substring MUST be smaller or equal in length to the original substring (len(replacement) <= len(original))\n"
        prompt += "- This length constraint is CRITICAL to maintain document layout and prevent text overflow\n"
        prompt += "- Choose shorter replacement words/phrases that still achieve the manipulation goal\n"

        # Add failure rationales if retrying
        if failure_rationales:
            prompt += "\n\nPREVIOUS ATTEMPTS FAILED:\n"
            for rationale in failure_rationales:
                prompt += f"- {rationale}\n"
            prompt += "\nPlease address these issues in your new mappings.\n"

        prompt += f"""

OUTPUT FORMAT (JSON only - STRICT SCHEMA):
You MUST return valid JSON matching this exact schema:
{{
  "mapping_sets": [
    {{
      "set_index": 1,
      "target_option": "{target_configs[0].get('target_option') if target_configs else None}",
      "target_option_text": "{target_configs[0].get('target_option_text') if target_configs else None}",
      "signal_strategy": "{target_configs[0].get('signal_strategy') if target_configs else None}",
      "mappings": [
        {{
          "original": "text to replace",
          "replacement": "replacement text",
          "start_pos": 0,
          "end_pos": 10,
          "context": "surrounding context"
        }}
      ]
      NOTE: Each set must have EXACTLY ONE mapping in the mappings array. The mapping can be as small as a single word (best case) or as large as the entire question stem substring (worst case).
    }},
    {{
      "set_index": 2,
      ...
    }},
    {{
      "set_index": 3,
      ...
    }}
  ]
}}

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {len(target_configs)} sets (set_index 1, 2, 3)
2. Each set must have EXACTLY ONE mapping targeting its specific configuration
3. Each mapping can range from a single word (best case) to the entire question stem substring (worst case)
4. Each set must have different mappings - do not repeat the same mapping across sets
5. Return ONLY valid JSON, no markdown, no code blocks, no explanations, no text before or after
6. Start with {{ and end with }}
7. LENGTH CONSTRAINT: The replacement substring MUST be smaller or equal in length to the original substring (len(replacement) <= len(original)). This is critical for maintaining document layout and preventing text overflow.
8. Ensure all JSON strings are properly escaped (use \\" for quotes inside strings)
9. Ensure all JSON is valid and can be parsed by json.loads() without errors

FEW-SHOT EXAMPLES:

Example 1 - Single word mapping (best case):
{{
  "mapping_sets": [
    {{
      "set_index": 1,
      "target_option": "A",
      "target_option_text": "Watt",
      "signal_strategy": null,
      "mappings": [
        {{"original": "power", "replacement": "work", "start_pos": 23, "end_pos": 28, "context": "SI unit of"}}
      ]
    }},
    {{
      "set_index": 2,
      "target_option": "C",
      "target_option_text": "Newton",
      "signal_strategy": null,
      "mappings": [
        {{"original": "power", "replacement": "force", "start_pos": 23, "end_pos": 28, "context": "SI unit of"}}
      ]
    }},
    {{
      "set_index": 3,
      "target_option": "D",
      "target_option_text": "Pascal",
      "signal_strategy": null,
      "mappings": [
        {{"original": "power", "replacement": "pressure", "start_pos": 23, "end_pos": 28, "context": "SI unit of"}}
      ]
    }}
  ]
}}

Example 2 - Phrase mapping (medium case):
{{
  "mapping_sets": [
    {{
      "set_index": 1,
      "target_option": "B",
      "target_option_text": "Refraction",
      "signal_strategy": null,
      "mappings": [
        {{"original": "splitting of white light", "replacement": "bending of light", "start_pos": 28, "end_pos": 54, "context": "causes the"}}
      ]
    }},
    {{
      "set_index": 2,
      "target_option": "C",
      "target_option_text": "Diffraction",
      "signal_strategy": null,
      "mappings": [
        {{"original": "prism", "replacement": "grating", "start_pos": 20, "end_pos": 25, "context": "in a"}}
      ]
    }},
    {{
      "set_index": 3,
      "target_option": "D",
      "target_option_text": "Polarization",
      "signal_strategy": null,
      "mappings": [
        {{"original": "constituent colors", "replacement": "wave direction", "start_pos": 55, "end_pos": 72, "context": "into its"}}
      ]
    }}
  ]
}}

Example 3 - Large substring mapping (worst case - entire question stem substring):
{{
  "mapping_sets": [
    {{
      "set_index": 1,
      "target_option": "A",
      "target_option_text": "Dispersion",
      "signal_strategy": null,
      "mappings": [
        {{"original": "What phenomenon in a prism causes the splitting of white light into its constituent colors?", "replacement": "What phenomenon in a prism causes the bending of light at different angles?", "start_pos": 0, "end_pos": 85, "context": ""}}
      ]
    }},
    {{
      "set_index": 2,
      "target_option": "B",
      "target_option_text": "Refraction",
      "signal_strategy": null,
      "mappings": [
        {{"original": "splitting of white light into its constituent colors", "replacement": "bending of light as it passes through", "start_pos": 28, "end_pos": 75, "context": "causes the"}}
      ]
    }},
    {{
      "set_index": 3,
      "target_option": "C",
      "target_option_text": "Diffraction",
      "signal_strategy": null,
      "mappings": [
        {{"original": "prism", "replacement": "grating", "start_pos": 20, "end_pos": 25, "context": "in a"}}
      ]
    }}
  ]
}}

IMPORTANT JSON FORMATTING RULES:
- Do NOT include markdown code blocks (no ```json or ```)
- Do NOT include any text before or after the JSON
- Do NOT include comments or explanations
- Escape all quotes inside strings: use \\" not "
- Ensure all brackets and braces are properly closed
- Ensure all commas are correctly placed
- Test your JSON mentally: it must parse as valid JSON

Return your response now as pure JSON following the schema above:
"""

        return prompt

    async def _validate_mapping_set_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        run_id: str,
        question_id: int,
        question_number: str,
        question_data: Dict[str, Any],
        mapping: Dict[str, Any],
        set_index: int,
        mapping_index: int,
        attempt: int,
        target_config: Dict[str, Any],
    ) -> ValidationResult:
        """Validate mapping with semaphore for concurrency control and timeout."""
        async with semaphore:
            try:
                # Wrap validation call with timeout to prevent infinite hangs
                # Use API_TIMEOUT (120s) as the timeout for each validation call
                validation_timeout = API_TIMEOUT
                return await asyncio.wait_for(
                    self._validate_mapping_set(
                        run_id=run_id,
                        question_id=question_id,
                        question_number=question_number,
                        question_data=question_data,
                        mapping=mapping,
                        set_index=set_index,
                        mapping_index=mapping_index,
                        attempt=attempt,
                        target_config=target_config,
                    ),
                    timeout=validation_timeout,
                )
            except asyncio.TimeoutError:
                self.logger.error(
                    f"Validation timeout after {validation_timeout}s",
                    run_id=run_id,
                    question_id=question_id,
                    set_index=set_index,
                    mapping_index=mapping_index,
                    attempt=attempt,
                )
                # Return failed validation result
                return ValidationResult(
                    is_valid=False,
                    confidence=0.0,
                    deviation_score=0.0,
                    reasoning=f"Validation timed out after {validation_timeout} seconds",
                    semantic_similarity=0.0,
                    factual_accuracy=False,
                    question_type_specific_notes="Timeout error",
                    gold_answer=question_data.get("gold_answer", ""),
                    test_answer="",
                    model_used="timeout"
                )

    async def _validate_mapping_set(
        self,
        run_id: str,
        question_id: int,
        question_number: str,
        question_data: Dict[str, Any],
        mapping: Dict[str, Any],
        set_index: int,
        mapping_index: int,
        attempt: int,
        target_config: Dict[str, Any],
    ) -> ValidationResult:
        """Validate a single mapping by getting test answer and validating deviation."""
        # Log before validation
        original_preview = mapping.get("original", "")[:50] + "..." if len(mapping.get("original", "")) > 50 else mapping.get("original", "")
        replacement_preview = mapping.get("replacement", "")[:50] + "..." if len(mapping.get("replacement", "")) > 50 else mapping.get("replacement", "")
        self.logger.debug(
            f"Validating mapping (set {set_index}, mapping {mapping_index})",
            run_id=run_id,
            question_id=question_id,
            attempt=attempt,
            set_index=set_index,
            mapping_index=mapping_index,
            original_preview=original_preview,
            replacement_preview=replacement_preview,
            target_option=target_config.get("target_option"),
        )

        # Apply mapping to question text
        question_text = question_data.get("stem_text", "")
        original = mapping.get("original", "")
        replacement = mapping.get("replacement", "")

        # Simple text replacement for validation
        manipulated_text = question_text.replace(original, replacement, 1)

        # Validate deviation - pass manipulated_question_text to let GPT-5.1 answer and validate in one call
        # This eliminates the need for the separate gpt-4o-mini call
        gold_answer = question_data.get("gold_answer", "")
        self.logger.debug(
            f"Validating with manipulated question: gold_answer={gold_answer}",
            run_id=run_id,
            question_id=question_id,
            set_index=set_index,
            mapping_index=mapping_index,
        )

        validation_result = await self.validator.validate_answer_deviation(
            question_text=question_text,
            question_type=question_data.get("question_type", "mcq_single"),
            gold_answer=gold_answer,
            test_answer=None,  # Let GPT-5.1 generate it from manipulated question
            manipulated_question_text=manipulated_text,  # Pass manipulated question
            options_data=question_data.get("options", {}),
            target_option=target_config.get("target_option"),
            target_option_text=target_config.get("target_option_text"),
            signal_metadata={"signal_strategy": target_config.get("signal_strategy")} if target_config.get("signal_strategy") else None,
            run_id=run_id,
        )

        # Log validation result
        self.logger.info(
            f"Validation result: is_valid={validation_result.is_valid}, confidence={validation_result.confidence:.3f}",
            run_id=run_id,
            question_id=question_id,
            attempt=attempt,
            set_index=set_index,
            mapping_index=mapping_index,
            is_valid=validation_result.is_valid,
            confidence=validation_result.confidence,
            deviation_score=validation_result.deviation_score,
            target_matched=validation_result.target_matched,
        )

        return validation_result

    # NOTE: _get_test_answer() method removed - we now use GPT-5.1 to answer and validate in one call
    # This eliminates the need for the separate gpt-4o-mini call, reducing latency and cost by ~50%

    async def _save_valid_mapping(
        self,
        run_id: str,
        question: QuestionManipulation,
        mapping: Dict[str, Any],
    ) -> None:
        """Save valid mapping to DB and structured.json with retry logic for SQLite locks."""
        mapping_preview = {
            "original": mapping.get("original", "")[:50] + "..." if len(mapping.get("original", "")) > 50 else mapping.get("original", ""),
            "replacement": mapping.get("replacement", "")[:50] + "..." if len(mapping.get("replacement", "")) > 50 else mapping.get("replacement", ""),
        }
        self.logger.info(
            f"Saving valid mapping for question {question.question_number}",
            run_id=run_id,
            question_id=question.id,
            mapping_preview=mapping_preview,
        )

        # Use semaphore to serialize database writes and prevent SQLite locks
        async with self._db_write_semaphore:
            max_retries = 5
            base_delay = 0.1  # Start with 100ms
            
            for attempt in range(max_retries):
                try:
                    # Convert single mapping to list format expected by DB
                    mappings_list = [mapping]

                    # Update question model
                    question.substring_mappings = mappings_list
                    db.session.add(question)
                    db.session.commit()

                    self.logger.debug(
                        f"Saved mapping to database",
                        run_id=run_id,
                        question_id=question.id,
                    )

                    # Sync to structured.json using SmartSubstitutionService
                    # This also needs to be protected by the semaphore
                    try:
                        from ...services.pipeline.smart_substitution_service import SmartSubstitutionService
                        service = SmartSubstitutionService()
                        service.sync_structured_mappings(run_id)
                    except Exception as sync_error:
                        # If sync fails, log but don't fail the whole operation
                        # The mapping is already saved to DB
                        error_type = type(sync_error).__name__
                        if "database is locked" in str(sync_error).lower():
                            # Retry the whole operation if sync fails due to lock
                            if attempt < max_retries - 1:
                                delay = base_delay * (2 ** attempt)
                                self.logger.warning(
                                    f"Database locked during sync, retrying in {delay}s (attempt {attempt + 1}/{max_retries})",
                                    run_id=run_id,
                                    question_id=question.id,
                                )
                                await asyncio.sleep(delay)
                                continue
                        self.logger.warning(
                            f"Failed to sync structured mappings (non-critical): {error_type}: {sync_error}",
                            run_id=run_id,
                            question_id=question.id,
                            error_type=error_type,
                        )

                    self.logger.info(
                        f"Successfully saved and synced valid mapping for question {question.question_number}",
                        run_id=run_id,
                        question_id=question.id,
                    )
                    return  # Success, exit retry loop

                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = str(e)
                    
                    # Check if it's a database lock error
                    is_lock_error = (
                        "database is locked" in error_msg.lower() or
                        "OperationalError" in error_type
                    )
                    
                    if is_lock_error and attempt < max_retries - 1:
                        # Exponential backoff for lock errors
                        delay = base_delay * (2 ** attempt)
                        self.logger.warning(
                            f"Database locked, retrying in {delay}s (attempt {attempt + 1}/{max_retries})",
                            run_id=run_id,
                            question_id=question.id,
                            error_type=error_type,
                        )
                        await asyncio.sleep(delay)
                        db.session.rollback()
                        continue
                    else:
                        # Not a lock error or max retries reached
                        self.logger.error(
                            f"Failed to save valid mapping: {error_type}: {error_msg}",
                            run_id=run_id,
                            question_id=question.id,
                            error_type=error_type,
                            error=error_msg,
                            attempt=attempt + 1,
                            exc_info=True,
                        )
                        db.session.rollback()
                        raise

    def get_question_status(
        self,
        run_id: str,
        question_id: int,
    ) -> Optional[QuestionGenerationStatus]:
        """Get generation status for a question."""
        return self._status_store.get(run_id, {}).get(question_id)

    def get_all_statuses(
        self,
        run_id: str,
    ) -> Dict[int, QuestionGenerationStatus]:
        """Get all question statuses for a run."""
        # Merge in-memory status with persisted status
        persisted = self._load_persisted_statuses_for_run(run_id)
        in_memory = self._status_store.get(run_id, {})
        # In-memory takes precedence if both exist
        merged = {**persisted, **in_memory}
        return merged

    def get_logs(
        self,
        run_id: str,
    ) -> List[Dict[str, Any]]:
        """Get logs for a run."""
        return self.mapping_logger.get_logs(run_id)

    def _persist_status(
        self,
        run_id: str,
        question_id: int,
        status: QuestionGenerationStatus,
    ) -> None:
        """Persist status to file (thread-safe)."""
        # Use lock to prevent concurrent file writes
        with self._status_file_lock:
            try:
                run_dir = run_directory(run_id)
                status_file = run_dir / "mapping_generation_status.json"
                
                # Load existing statuses
                if status_file.exists():
                    try:
                        with open(status_file, 'r') as f:
                            data = json.load(f)
                    except (json.JSONDecodeError, IOError) as e:
                        self.logger.warning(
                            f"Failed to load existing status file, creating new one: {e}",
                            run_id=run_id,
                            question_id=question_id,
                        )
                        data = {}
                else:
                    data = {}
                
                # Update status for this question
                if run_id not in data:
                    data[run_id] = {}
                
                # Convert dataclass to dict
                status_dict = {
                    "question_id": status.question_id,
                    "question_number": status.question_number,
                    "status": status.status,
                    "retry_count": status.retry_count,
                    "current_attempt": status.current_attempt,
                    "mapping_sets_generated": [
                        {
                            "attempt": ms.attempt,
                            "set_index": ms.set_index,
                            "target_option": ms.target_option,
                            "signal_strategy": ms.signal_strategy,
                            "mappings_count": ms.mappings_count,
                            "generated_at": ms.generated_at,
                        }
                        for ms in status.mapping_sets_generated
                    ],
                    "validation_outcomes": [
                        {
                            "attempt": vo.attempt,
                            "set_index": vo.set_index,
                            "mapping_index": vo.mapping_index,
                            "is_valid": vo.is_valid,
                            "confidence": vo.confidence,
                            "deviation_score": vo.deviation_score,
                            "reasoning": vo.reasoning,
                            "test_answer": vo.test_answer,
                            "target_matched": vo.target_matched,
                            "validated_at": vo.validated_at,
                        }
                        for vo in status.validation_outcomes
                    ],
                    "failure_rationales": status.failure_rationales,
                    "generation_exceptions": status.generation_exceptions,
                    "valid_mapping": status.valid_mapping,
                    "error": status.error,
                    "started_at": status.started_at,
                    "completed_at": status.completed_at,
                }
                
                data[run_id][str(question_id)] = status_dict
                
                # Save to file
                status_file.parent.mkdir(parents=True, exist_ok=True)
                with open(status_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                self.logger.warning(
                    f"Failed to persist status for question {question_id}: {e}",
                    run_id=run_id,
                    question_id=question_id,
                    exc_info=True,
                )

    def _load_persisted_statuses(self) -> None:
        """Load all persisted statuses on init (for all runs)."""
        # This is called on init, but we'll load on-demand per run
        pass

    def _load_persisted_statuses_for_run(
        self,
        run_id: str,
    ) -> Dict[int, QuestionGenerationStatus]:
        """Load persisted statuses for a specific run."""
        try:
            run_dir = run_directory(run_id)
            status_file = run_dir / "mapping_generation_status.json"
            
            if not status_file.exists():
                return {}
            
            with open(status_file, 'r') as f:
                data = json.load(f)
            
            run_data = data.get(run_id, {})
            statuses = {}
            
            for qid_str, status_dict in run_data.items():
                try:
                    question_id = int(qid_str)
                    statuses[question_id] = QuestionGenerationStatus(
                        question_id=status_dict["question_id"],
                        question_number=status_dict["question_number"],
                        status=status_dict["status"],
                        retry_count=status_dict.get("retry_count", 0),
                        current_attempt=status_dict.get("current_attempt", 1),
                        mapping_sets_generated=[
                            MappingSetStatus(
                                attempt=ms["attempt"],
                                set_index=ms["set_index"],
                                target_option=ms.get("target_option"),
                                signal_strategy=ms.get("signal_strategy"),
                                mappings_count=ms.get("mappings_count", 0),
                                generated_at=ms.get("generated_at", isoformat(utc_now())),
                            )
                            for ms in status_dict.get("mapping_sets_generated", [])
                        ],
                        validation_outcomes=[
                            ValidationOutcome(
                                attempt=vo["attempt"],
                                set_index=vo["set_index"],
                                mapping_index=vo["mapping_index"],
                                is_valid=vo["is_valid"],
                                confidence=vo["confidence"],
                                deviation_score=vo["deviation_score"],
                                reasoning=vo["reasoning"],
                                test_answer=vo["test_answer"],
                                target_matched=vo.get("target_matched"),
                                validated_at=vo.get("validated_at", isoformat(utc_now())),
                            )
                            for vo in status_dict.get("validation_outcomes", [])
                        ],
                        failure_rationales=status_dict.get("failure_rationales", []),
                        generation_exceptions=status_dict.get("generation_exceptions", []),
                        valid_mapping=status_dict.get("valid_mapping"),
                        error=status_dict.get("error"),
                        started_at=status_dict.get("started_at", isoformat(utc_now())),
                        completed_at=status_dict.get("completed_at"),
                    )
                except (KeyError, ValueError, TypeError) as e:
                    self.logger.warning(
                        f"Failed to load status for question {qid_str}: {e}",
                        run_id=run_id,
                        exc_info=True,
                    )
                    continue
            
            return statuses
        except Exception as e:
            self.logger.warning(
                f"Failed to load persisted statuses for run {run_id}: {e}",
                run_id=run_id,
                exc_info=True,
            )
            return {}

