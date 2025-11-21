from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request
import json
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text

from ..extensions import db
from ..models import AIModelResult, PipelineRun, QuestionManipulation
from ..services.intelligence.multi_model_tester import MultiModelTester
from ..services.pipeline.smart_substitution_service import SmartSubstitutionService
from ..services.manipulation.substring_manipulator import SubstringManipulator
from ..services.validation.gpt5_validation_service import GPT5ValidationService, ValidationResult
from ..utils.logging import get_logger
from ..services.pipeline.auto_mapping_strategy import (
    describe_strategy_for_validation,
    get_strategy,
)
from ..utils.exceptions import ResourceNotFound
from ..services.mapping.gpt5_config import MAPPINGS_PER_QUESTION
from ..services.mapping.mapping_generation_coordinator import get_mapping_generation_coordinator
from ..services.mapping.mapping_generation_logger import get_mapping_logger
from ..services.mapping.mapping_staging_service import MappingStagingService


bp = Blueprint("questions", __name__, url_prefix="/questions")

logger = get_logger(__name__)


def _ranges_overlap(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
	return max(a[0], b[0]) < min(a[1], b[1])


def _has_overlaps(mappings: List[Dict[str, Any]]) -> bool:
	sorted_ranges = sorted(
		[
			(
				int(entry.get("start_pos", 0)),
				int(entry.get("end_pos", 0)),
			)
			for entry in mappings
		],
		key=lambda item: item[0],
	)
	for idx in range(1, len(sorted_ranges)):
		if _ranges_overlap(sorted_ranges[idx - 1], sorted_ranges[idx]):
			return True
	return False


def _canonicalize_mappings_for_compare(mappings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
	canonical: List[Dict[str, Any]] = []
	for entry in mappings:
		start_pos = entry.get("start_pos")
		end_pos = entry.get("end_pos")
		if start_pos is None or end_pos is None:
			continue
		try:
			start_pos_int = int(start_pos)
			end_pos_int = int(end_pos)
		except (TypeError, ValueError):
			continue
		canonical.append(
			{
				"original": entry.get("original"),
				"replacement": entry.get("replacement"),
				"start_pos": start_pos_int,
				"end_pos": end_pos_int,
				"context": entry.get("context", "question_stem"),
			}
		)
	canonical.sort(key=lambda item: (item["start_pos"], item["end_pos"], item["original"] or ""))
	return canonical


def init_app(api_bp: Blueprint) -> None:
	api_bp.register_blueprint(bp)


@bp.get("/<run_id>")
def list_questions(run_id: str):
	from ..services.data_management.structured_data_manager import StructuredDataManager

	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

	questions = (
		QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
		.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
		.all()
	)

	# Load structured data to get rich question content
	structured_manager = StructuredDataManager()
	structured = structured_manager.load(run_id)
	ai_questions = structured.get("ai_questions", [])

	# Create a mapping of question numbers to AI questions for rich content
	ai_question_map = {str(q.get("question_number", q.get("q_number", ""))): q for q in ai_questions}

	return jsonify(
		{
			"run_id": run.id,
			"questions": [
				{
					"id": question.id,
					"question_number": question.question_number,
					"sequence_index": question.sequence_index,
					"question_type": question.question_type,
					"source_identifier": question.source_identifier,
					"original_text": question.original_text,
					# Use rich AI extraction data if available, fallback to original_text
					"stem_text": (
						ai_question_map.get(str(question.question_number), {}).get("stem_text")
						or question.original_text
					),
					"options_data": (
						ai_question_map.get(str(question.question_number), {}).get("options")
						or question.options_data
					),
					"gold_answer": question.gold_answer,
					"gold_confidence": question.gold_confidence,
                    "question_id": (
                        ai_question_map.get(str(question.question_number), {}).get("question_id")
                        or (question.ai_model_results or {}).get("manual_seed", {}).get("question_id")
                    ),
                    "marks": (
                        (ai_question_map.get(str(question.question_number), {}).get("metadata") or {}).get("marks")
                        or (question.ai_model_results or {}).get("manual_seed", {}).get("marks")
                    ),
                    "answer_explanation": (
                        (ai_question_map.get(str(question.question_number), {}).get("metadata") or {}).get("explanation")
                        or (question.ai_model_results or {}).get("manual_seed", {}).get("explanation")
                    ),
                    "has_image": (
                        (ai_question_map.get(str(question.question_number), {}).get("metadata") or {}).get("has_image")
                        or (question.ai_model_results or {}).get("manual_seed", {}).get("has_image")
                    ),
                    "image_path": (
                        (ai_question_map.get(str(question.question_number), {}).get("metadata") or {}).get("image_path")
                        or (question.ai_model_results or {}).get("manual_seed", {}).get("image_path")
                    ),
					"manipulation_method": question.manipulation_method,
					"effectiveness_score": question.effectiveness_score,
					"substring_mappings": question.substring_mappings or [],
					"ai_model_results": question.ai_model_results or {},
                    "visual_elements": question.visual_elements or [],
					# Additional AI extraction metadata
					"confidence": ai_question_map.get(str(question.question_number), {}).get("confidence"),
					"positioning": ai_question_map.get(str(question.question_number), {}).get("positioning"),
				}
				for question in questions
			],
			"total": len(questions),
		}
	)


@bp.post("/<run_id>/gold/refresh")
def refresh_true_gold(run_id: str):
	"""Compute or refresh true gold answers for all questions in a run."""
	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

	service = SmartSubstitutionService()
	# Reuse internal method via run() which now computes gold at smart_substitution stage
	# Here we only recompute gold fields without altering mappings
	questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
	updated = 0
	for q in questions:
		gold, conf = service._compute_true_gold(q)  # internal use
		q.gold_answer = gold
		q.gold_confidence = conf
		db.session.add(q)
		updated += 1
	db.session.commit()
	return jsonify({"updated": updated})


@bp.put("/<run_id>/<int:question_id>/manipulation")
def update_manipulation(run_id: str, question_id: int):
	question = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
	if not question:
		return jsonify({"error": "Question manipulation not found"}), HTTPStatus.NOT_FOUND

	payload = request.json or {}
	method = payload.get("method")
	substring_mappings = payload.get("substring_mappings", [])
	custom_mappings = payload.get("custom_mappings")

	service = SmartSubstitutionService()
	normalized = [service._normalize_mapping_entry(entry) for entry in substring_mappings]
	try:
		enriched = service._enrich_selection_geometry(run_id, question, normalized)
	except ValueError as exc:
		return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

	question.manipulation_method = method
	question.substring_mappings = enriched
	# Use raw SQL to bypass mutable tracking issues
	db.session.execute(
		text("UPDATE question_manipulations SET substring_mappings = :mappings WHERE id = :id"),
		{"mappings": json.dumps(enriched), "id": question.id}
	)
	if custom_mappings:
		question.ai_model_results = question.ai_model_results or {}
		question.ai_model_results["custom_mappings"] = custom_mappings

	db.session.add(question)
	db.session.commit()

	if payload.get("regenerate_mappings"):
		service.refresh_question_mapping(run_id, str(question.id))

	service.sync_structured_mappings(run_id)

	updated_entry = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
	return jsonify(
		{
			"status": "updated",
			"question_id": question.id,
			"method": method,
			"substring_mappings": enriched,
			"effectiveness_score": updated_entry.effectiveness_score if updated_entry else None,
		}
	)
	# response already returned above


@bp.post("/<run_id>/<int:question_id>/validate")
def validate_mapping(run_id: str, question_id: int):
	"""Enhanced validation using GPT-5 intelligent answer comparison.
	Applies mappings, gets model response, then uses GPT-5 to compare with gold answer.
	Returns detailed validation results with confidence scores and deviation analysis.
	"""
	from ..services.data_management.structured_data_manager import StructuredDataManager

	question = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
	if not question:
		return jsonify({"error": "Question manipulation not found"}), HTTPStatus.NOT_FOUND

	payload = request.json or {}
	mappings = payload.get("substring_mappings", [])
	# model parameter no longer used - we use GPT-5.1 directly
	# Step 1: Apply mappings to create modified question
	manipulator = SubstringManipulator()
	try:
		structured = StructuredDataManager().load(run_id)
		ai_map = {str(q.get("question_number", q.get("q_number", ""))): q for q in structured.get("ai_questions", [])}
		rich = ai_map.get(str(question.question_number), {})
		source_text = rich.get("stem_text") or question.original_text or ""
		service = SmartSubstitutionService()
		normalized_entries = [service._normalize_mapping_entry(entry) for entry in mappings]
		normalized_entries = [entry for entry in normalized_entries if entry.get("start_pos") is not None and entry.get("end_pos") is not None]
		if not normalized_entries:
			return jsonify({"error": "No valid mappings supplied for validation"}), HTTPStatus.BAD_REQUEST
		if _has_overlaps(normalized_entries):
			return jsonify({"error": "Mappings must not overlap"}), HTTPStatus.BAD_REQUEST
		ordered_entries = sorted(normalized_entries, key=lambda item: int(item.get("start_pos", 0)))

		existing_mappings = question.substring_mappings or []
		if existing_mappings:
			existing_normalized = [
				service._normalize_mapping_entry(entry)
				for entry in existing_mappings
				if entry.get("start_pos") is not None and entry.get("end_pos") is not None
			]
			existing_canonical = _canonicalize_mappings_for_compare(existing_normalized)
			requested_canonical = _canonicalize_mappings_for_compare(ordered_entries)
			if (
				existing_canonical == requested_canonical
				and all(bool(entry.get("validated")) for entry in existing_mappings)
			):
				last_validation = (question.ai_model_results or {}).get("last_validation")
				return jsonify(
					{
						"status": "already_validated",
						"substring_mappings": existing_mappings,
						"last_validation": last_validation,
					}
				)

		modified = manipulator.apply_mappings_to_text(source_text, ordered_entries)
	except ValueError as exc:
		return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

	# Use optimized GPT-5.1 validation that answers and validates in one call
	# This eliminates the need for the separate gpt-4o call
	strategy_definition = get_strategy(question.question_type or "mcq_single")
	strategy_validation_focus = describe_strategy_for_validation(strategy_definition)

	validator = GPT5ValidationService()
	question_type = question.question_type or "mcq_single"
	if validator.is_configured():
		import asyncio
		validation_result = asyncio.run(validator.validate_answer_deviation(
			question_text=source_text,  # Original question text
			question_type=question_type,
			gold_answer=question.gold_answer or "",
			test_answer=None,  # Let GPT-5.1 generate it from manipulated question
			manipulated_question_text=modified,  # Pass manipulated question
			options_data=question.options_data,
			target_option=None,
			target_option_text=None,
			signal_metadata=None,
			run_id=run_id,
		))
		# Extract test_answer from validation result
		test_answer = validation_result.test_answer or ""
	else:
		# Fallback to offline heuristic if GPT-5.1 not configured
		test_answer = ""
		deviation = 0.8 if (question.gold_answer or "").strip().lower() != test_answer.strip().lower() else 0.2
		confidence = 0.65 if deviation >= 0.5 else 0.3
		validation_result = ValidationResult(
			is_valid=deviation >= 0.5,
			confidence=confidence,
			deviation_score=deviation,
			reasoning="Offline heuristic validation (no GPT-5 configuration)",
			semantic_similarity=1.0 - deviation,
			factual_accuracy=False,
			question_type_specific_notes=strategy_validation_focus,
			gold_answer=question.gold_answer or "",
			test_answer=test_answer,
			model_used="offline-heuristic",
		)

	# Step 4: Create comprehensive validation record
	strategy_info = (question.ai_model_results or {}).get("auto_generated", {}).get("strategy")
	validation_record = {
		"model": "gpt-5.1" if validator.is_configured() else "offline",
		"response": test_answer,
		"gold": question.gold_answer,
		"prompt_len": len(modified),
		"strategy": strategy_info,
		"strategy_focus": strategy_validation_focus,
		"gpt5_validation": {
			"is_valid": validation_result.is_valid,
			"confidence": validation_result.confidence,
			"deviation_score": validation_result.deviation_score,
			"reasoning": validation_result.reasoning,
			"semantic_similarity": validation_result.semantic_similarity,
			"factual_accuracy": validation_result.factual_accuracy,
			"question_type_notes": validation_result.question_type_specific_notes,
			"model_used": validation_result.model_used,
			"threshold": validator.get_validation_threshold(question.question_type or "mcq_single"),
		},
	}

	# Step 5: Update question records
	question.ai_model_results = question.ai_model_results or {}
	question.ai_model_results["last_validation"] = {
		**validation_record,
		"gpt5_validation": {
			"is_valid": validation_result.is_valid,
			"confidence": validation_result.confidence,
			"deviation_score": validation_result.deviation_score,
			"reasoning": validation_result.reasoning,
			"semantic_similarity": validation_result.semantic_similarity,
			"factual_accuracy": validation_result.factual_accuracy,
			"question_type_notes": validation_result.question_type_specific_notes,
			"model_used": validation_result.model_used,
			"threshold": validator.get_validation_threshold(question_type),
		},
		"strategy": strategy_info,
	}

	if question.substring_mappings:
		updated_mappings: List[Dict[str, Any]] = []
		for existing in question.substring_mappings:
			entry = dict(existing)
			entry["validated"] = validation_result.is_valid
			entry["confidence"] = validation_result.confidence
			entry["deviation_score"] = validation_result.deviation_score
			entry["validation"] = validation_record
			updated_mappings.append(entry)
		question.substring_mappings = updated_mappings
		# ensure ORM notices change for mutable JSON columns
		db.session.execute(
			text("UPDATE question_manipulations SET substring_mappings = :mappings WHERE id = :id"),
			{"mappings": json.dumps(updated_mappings), "id": question.id},
		)

	db.session.add(question)
	db.session.commit()

	return jsonify(
		{
			"run_id": run_id,
			"question_id": question.id,
			"gold_answer": question.gold_answer,
			"model": "gpt-5.1" if validator.is_configured() else "offline",
			"modified_question": modified,
			"model_response": {"provider": "gpt-5.1", "response": test_answer},
			"substring_mappings": question.substring_mappings or [],
			"gpt5_validation": {
				"is_valid": validation_result.is_valid,
				"confidence": validation_result.confidence,
				"deviation_score": validation_result.deviation_score,
				"reasoning": validation_result.reasoning,
				"semantic_similarity": validation_result.semantic_similarity,
				"factual_accuracy": validation_result.factual_accuracy,
				"question_type_notes": validation_result.question_type_specific_notes,
				"threshold_used": validator.get_validation_threshold(question.question_type or "mcq_single"),
				"validation_passed": validation_result.is_valid,
			},
		}
	)


@bp.post("/<run_id>/<int:question_id>/auto_generate")
def auto_generate_mappings(run_id: str, question_id: int):
	"""Generate substring mappings via GPT-5 based on question context."""
	question = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
	if not question:
		return jsonify({"error": "Question manipulation not found"}), HTTPStatus.NOT_FOUND

	payload = request.json or {}
	# Use GPT-5.1 explicitly for mapping generation, not fusion which defaults to gpt-4o
	model = payload.get("model", "openai:gpt-5.1")
	force_refresh = bool(payload.get("force"))
	# Use new streamlined service instead of old auto_generate_for_question
	from ..services.mapping.streamlined_mapping_service import StreamlinedMappingService
	import asyncio
	import threading
	from flask import current_app
	
	service = StreamlinedMappingService()
	app = current_app._get_current_object()
	
	# Run async generation synchronously for this endpoint
	result = None
	error = None
	
	def run_generation():
		nonlocal result, error
		with app.app_context():
			try:
				# Create a new event loop for this thread
				loop = asyncio.new_event_loop()
				asyncio.set_event_loop(loop)
				try:
					result = loop.run_until_complete(service.generate_mappings_for_single_question(run_id, question_id))
				finally:
					# Ensure all pending tasks complete before closing
					pending = asyncio.all_tasks(loop)
					if pending:
						loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
					loop.close()
			except Exception as e:
				error = e
	
	thread = threading.Thread(target=run_generation)
	thread.start()
	thread.join()
	
	if error:
		logger.error(f"Auto-generation failed for question {question_id}: {error}", exc_info=True)
		return jsonify({"error": str(error)}), HTTPStatus.INTERNAL_SERVER_ERROR
	
	if not result or result.get("status") != "success":
		return jsonify({
			"run_id": run_id,
			"question_id": question.id,
			"error": result.get("error") if result else "Unknown error",
			"failure_rationales": result.get("failure_rationales", []) if result else [],
		}), HTTPStatus.INTERNAL_SERVER_ERROR
	
	valid_mapping = result.get("valid_mapping")
	if not valid_mapping:
		return jsonify({
			"run_id": run_id,
			"question_id": question.id,
			"error": "No valid mapping generated",
		}), HTTPStatus.INTERNAL_SERVER_ERROR
	
	# Update question with valid mapping
	question.substring_mappings = [valid_mapping]
	question.manipulation_method = question.manipulation_method or "smart_substitution"
	
	db.session.add(question)
	db.session.commit()
	
	# Sync to structured.json
	smart_service = SmartSubstitutionService()
	try:
		smart_service.sync_structured_mappings(run_id)
	except Exception as sync_exc:  # noqa: BLE001
		logger.warning(
			"auto_generate sync failed",
			run_id=run_id,
			question_id=question_id,
			error=str(sync_exc),
		)
	
	return jsonify(
		{
			"run_id": run_id,
			"question_id": question.id,
			"substring_mappings": [valid_mapping],
			"status": "success",
		}
	)


@bp.post("/<run_id>/<int:question_id>/test")
def test_question(run_id: str, question_id: int):
	tester = MultiModelTester()
	payload = request.json or {}
	models = payload.get("models")

	try:
		results = tester.test_question(run_id, question_id, models=models)
	except ResourceNotFound as exc:
		return jsonify({"error": str(exc)}), HTTPStatus.NOT_FOUND

	return jsonify(results)


@bp.get("/<run_id>/<int:question_id>/history")
def question_history(run_id: str, question_id: int):
	return jsonify({"run_id": run_id, "question_id": question_id, "history": []})


@bp.post("/<run_id>/bulk-save-mappings")
def bulk_save_mappings(run_id: str):
	"""Save mappings for multiple questions at once - used by UI."""
	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

	payload = request.json or {}
	questions_data = payload.get("questions", [])

	if not questions_data:
		return jsonify({"error": "No questions data provided"}), HTTPStatus.BAD_REQUEST

	service = SmartSubstitutionService()
	updated_count = 0
	errors = []
	updated_payloads: Dict[int, List[Dict[str, Any]]] = {}

	for question_data in questions_data:
		question_id = question_data.get("id")
		substring_mappings = question_data.get("substring_mappings", [])
		manipulation_method = question_data.get("manipulation_method", "smart_substitution")

		question = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
		if not question:
			errors.append(f"Question {question_id} not found")
			continue

		try:
			normalized = [service._normalize_mapping_entry(entry) for entry in substring_mappings]
			enriched = service._enrich_selection_geometry(run_id, question, normalized)
		except ValueError as exc:
			errors.append(f"Question {question_id}: {exc}")
			continue
		try:
			question.manipulation_method = manipulation_method
			question.substring_mappings = enriched
			# Use raw SQL to bypass mutable tracking issues with JSONB
			db.session.execute(
				text("UPDATE question_manipulations SET substring_mappings = :mappings WHERE id = :id"),
				{"mappings": json.dumps(enriched), "id": question.id}
			)
			db.session.add(question)
			updated_count += 1
			updated_payloads[question.id] = enriched
		except Exception as e:
			errors.append(f"Question {question_id}: {str(e)}")

	try:
		db.session.commit()
	except Exception as e:
		db.session.rollback()
		return jsonify({"error": f"Failed to save mappings: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR

	service.sync_structured_mappings(run_id)

	result = {
		"run_id": run_id,
		"updated_count": updated_count,
		"total_questions": len(questions_data),
		"updated_questions": updated_payloads,
	}

	if errors:
		result["errors"] = errors

	return jsonify(result)


@bp.post("/<run_id>/generate-mappings")
def generate_mappings_for_all(run_id: str):
	"""Generate mappings for all questions asynchronously using streamlined service."""
	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND
	
	try:
		from ..services.mapping.streamlined_mapping_service import StreamlinedMappingService
		import threading
		from flask import current_app
		
		service = StreamlinedMappingService()
		app = current_app._get_current_object()
		
		# Run async generation in background thread with proper event loop management
		def run_generation():
			with app.app_context():
				import asyncio
				# Create a new event loop for this thread
				loop = asyncio.new_event_loop()
				asyncio.set_event_loop(loop)
				try:
					loop.run_until_complete(service.generate_mappings_for_all_questions(run_id))
				finally:
					# Ensure all pending tasks complete before closing
					pending = asyncio.all_tasks(loop)
					if pending:
						loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
					loop.close()
		
		thread = threading.Thread(target=run_generation, daemon=True)
		thread.start()
		
		return jsonify({"run_id": run_id, "status": "started"}), HTTPStatus.ACCEPTED
	except Exception as e:  # pragma: no cover - defensive
		logger.error(f"Failed to start mapping generation for run {run_id}: {e}")
		return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@bp.post("/<run_id>/<int:question_id>/generate-mappings")
def generate_mappings_for_question(run_id: str, question_id: int):
	"""Generate mappings for a single question using streamlined service."""
	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND
	
	try:
		from ..services.mapping.streamlined_mapping_service import StreamlinedMappingService
		import threading
		from flask import current_app
		
		service = StreamlinedMappingService()
		app = current_app._get_current_object()
		
		# Run async generation in background thread with proper event loop management
		def run_generation():
			with app.app_context():
				import asyncio
				# Create a new event loop for this thread
				loop = asyncio.new_event_loop()
				asyncio.set_event_loop(loop)
				try:
					loop.run_until_complete(service.generate_mappings_for_single_question(run_id, question_id))
				finally:
					# Ensure all pending tasks complete before closing
					pending = asyncio.all_tasks(loop)
					if pending:
						loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
					loop.close()
		
		thread = threading.Thread(target=run_generation, daemon=True)
		thread.start()
		
		return jsonify({"run_id": run_id, "question_id": question_id, "status": "started"}), HTTPStatus.ACCEPTED
	except ValueError as e:
		return jsonify({"error": str(e)}), HTTPStatus.NOT_FOUND
	except Exception as e:  # pragma: no cover - defensive
		logger.error(f"Failed to start mapping generation for question {question_id}: {e}")
		return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@bp.get("/<run_id>/generation-status")
def get_generation_status(run_id: str):
	"""Get status of mapping generation using streamlined service."""
	from ..services.mapping.streamlined_mapping_service import StreamlinedMappingService
	
	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND
	
	try:
		service = StreamlinedMappingService()
		all_statuses = service.get_all_statuses(run_id)
		logs = service.get_logs(run_id)

		# Calculate status summary from streamlined service
		questions = (
			QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
			.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
			.all()
		)
		status_summary = {}
		
		for question in questions:
			key = str(question.id)
			status = all_statuses.get(question.id)
			
			if status:
				# Compute mappings_generated from mapping_sets_generated
				mappings_generated = sum(ms.mappings_count for ms in status.mapping_sets_generated)
				
				# Compute mappings_validated from validation_outcomes
				mappings_validated = len(status.validation_outcomes)
				
				# Map status to display status (for frontend compatibility)
				status_display = status.status
				if status.status in ["generating", "validating", "retrying"]:
					status_display = "running"
				
				# Convert dataclass to dict
				status_dict = {
					"question_id": status.question_id,
					"question_number": status.question_number,
					"status": status.status,
					"status_display": status_display,  # For frontend compatibility
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
					# Computed fields for frontend compatibility
					"mappings_generated": mappings_generated,
					"mappings_validated": mappings_validated,
				}
				status_summary[key] = status_dict
			else:
				# Question not yet started
				status_summary[key] = {
					"question_id": question.id,
					"question_number": question.question_number,
					"status": "pending",
					"status_display": "pending",
					"retry_count": 0,
					"current_attempt": 0,
					"mapping_sets_generated": [],
					"validation_outcomes": [],
					"failure_rationales": [],
					"generation_exceptions": [],
					"valid_mapping": None,
					"error": None,
					"started_at": None,
					"completed_at": None,
					"mappings_generated": 0,
					"mappings_validated": 0,
				}
		
		# Load staged mappings
		from ..services.mapping.mapping_staging_service import MappingStagingService
		staging_service = MappingStagingService()
		staged = staging_service.load(run_id)
		
		return jsonify({
			"run_id": run_id,
			"total_questions": len(questions),
			"status_summary": status_summary,
			"logs": logs,
			"staged": staged.get("questions", {}),
		})
	except Exception as e:
		logger.error(f"Failed to get generation status for run {run_id}: {e}")
		return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@bp.get("/<run_id>/generation-logs")
def get_generation_logs(run_id: str):
	"""Get detailed logs for mapping generation."""
	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND
	
	try:
		logger_service = get_mapping_logger()
		staging_service = MappingStagingService()
		logger_service.load_logs(run_id)
		logs = logger_service.get_logs(run_id)
		staged_snapshot = staging_service.load(run_id)
		
		return jsonify({
			"run_id": run_id,
			"logs": logs,
			"staged": staged_snapshot.get("questions", {}),
		})
	except Exception as e:
		logger.error(f"Failed to get generation logs for run {run_id}: {e}")
		return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR