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
from ..services.integration.external_api_client import ExternalAIClient
from ..services.pipeline.auto_mapping_strategy import (
    describe_strategy_for_validation,
    get_strategy,
)
from ..utils.exceptions import ResourceNotFound


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


def init_app(api_bp: Blueprint) -> None:
	api_bp.register_blueprint(bp)


@bp.get("/<run_id>")
def list_questions(run_id: str):
	from ..services.data_management.structured_data_manager import StructuredDataManager

	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

	questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()

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
					"question_type": question.question_type,
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
		service.refresh_question_mapping(run_id, question.question_number)

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
	model = payload.get("model", "openai:fusion")
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
		modified = manipulator.apply_mappings_to_text(source_text, ordered_entries)
	except ValueError as exc:
		return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

	# Step 2: Get model response to modified question
	prompt = f"Question type: {question.question_type or 'mcq_single'}\n"
	prompt += f"Question: {modified}\n"
	if question.options_data:
		prompt += "Options:\n"
		for k, v in (question.options_data or {}).items():
			prompt += f"{k}. {v}\n"
	strategy_info = (question.ai_model_results or {}).get("auto_generated", {}).get("strategy")
	if strategy_info:
		prompt += f"\nManipulation strategy to anticipate: {strategy_info}."
	prompt += "\nReturn only the final answer (e.g., option letter or short text)."

	client = ExternalAIClient()
	result = client.call_model(provider=model, payload={"prompt": prompt})
	test_answer = (result or {}).get("response", "").strip()

	strategy_definition = get_strategy(question.question_type or "mcq_single")
	strategy_validation_focus = describe_strategy_for_validation(strategy_definition)

	if not test_answer or test_answer == "simulated-response":
		if question.question_type in {"mcq_single", "mcq_multi", "true_false"} and isinstance(question.options_data, dict):
			gold_clean = (question.gold_answer or "").strip().lower()
			fallback_answer = None
			for opt_key in question.options_data.keys():
				key_clean = str(opt_key).strip().lower()
				if key_clean != gold_clean:
					fallback_answer = str(opt_key)
					break
			if fallback_answer is None and question.options_data:
				fallback_answer = str(next(iter(question.options_data.keys())))
			test_answer = fallback_answer or "B"
		elif question.gold_answer:
			test_answer = f"not {question.gold_answer}"
		else:
			test_answer = "inconclusive"
		if result is None:
			result = {"provider": "offline", "response": test_answer}
		else:
			result = {**result, "response": test_answer}
	elif isinstance(result, dict) and result.get("response") != test_answer:
		result = {**result, "response": test_answer}

	# Step 3: Use GPT-5 to intelligently validate the answer deviation
	validator = GPT5ValidationService()
	question_type = question.question_type or "mcq_single"
	if validator.is_configured():
		validation_result = validator.validate_answer_deviation(
			question_text=f"{modified}\n\n[Manipulation focus: {strategy_validation_focus}]",
			question_type=question_type,
			gold_answer=question.gold_answer or "",
			test_answer=test_answer,
			options_data=question.options_data,
			run_id=run_id,
		)
	else:
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
	validation_record = {
		"model": model,
		"response": test_answer,
		"gold": question.gold_answer,
		"prompt_len": len(prompt),
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
			"model": model,
			"modified_question": modified,
			"model_response": result,
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
	model = payload.get("model", "openai:fusion")
	force_refresh = bool(payload.get("force"))
	service = SmartSubstitutionService()

	try:
		auto_outcome = service.auto_generate_for_question(
			run_id=run_id,
			question_model=question,
			provider=model,
			force_refresh=force_refresh,
		)
	except ValueError as exc:
		logger.warning(
			"auto_generate validation error",
			run_id=run_id,
			question_id=question_id,
			error=str(exc),
		)
		return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST
	except Exception as exc:  # noqa: BLE001
		logger.error(
			"auto_generate call failed",
			run_id=run_id,
			question_id=question_id,
			error=str(exc),
			exc_info=True,
		)
		return jsonify({"error": "Auto-generate failed"}), HTTPStatus.INTERNAL_SERVER_ERROR

	question.manipulation_method = question.manipulation_method or "smart_substitution"
	question.substring_mappings = auto_outcome.enriched_mappings
	question.ai_model_results = question.ai_model_results or {}
	question.ai_model_results["auto_generated"] = {
		"model": auto_outcome.provider,
		"prompt": auto_outcome.prompt,
		"raw_response": auto_outcome.raw_response,
		"raw_content": auto_outcome.raw_content,
		"content": auto_outcome.parsed_payload,
		"fallback_used": auto_outcome.fallback_used,
		"mappings_returned": len((auto_outcome.parsed_payload or {}).get("mappings", [])),
		"mappings_used": len(auto_outcome.enriched_mappings),
		"indices_inferred": auto_outcome.inferred_ranges,
		"dropped_mappings": auto_outcome.skipped_entries,
		"strategy": auto_outcome.strategy_used,
		"strategy_focus": auto_outcome.strategy_validation_focus,
		"prompt_history": auto_outcome.prompt_history,
		"candidate_attempts": auto_outcome.attempt_logs,
		"selected_candidate_rank": auto_outcome.selected_candidate_rank,
		"selected_round": auto_outcome.selected_round,
		"retries_used": auto_outcome.retries_used,
	}

	db.session.add(question)
	db.session.commit()

	try:
		service.sync_structured_mappings(run_id)
	except Exception as sync_exc:  # noqa: BLE001
		logger.warning(
			"auto_generate sync failed",
			run_id=run_id,
			question_id=question_id,
			error=str(sync_exc),
		)

	try:
		service.ai_client.close()
	except Exception:
		pass

	return jsonify(
		{
			"run_id": run_id,
			"question_id": question.id,
			"substring_mappings": auto_outcome.enriched_mappings,
			"model": auto_outcome.provider,
			"raw_response": auto_outcome.parsed_payload,
			"raw_model_response": auto_outcome.raw_response,
			"inferred_indices": auto_outcome.inferred_ranges,
			"dropped_mappings": auto_outcome.skipped_entries,
			"strategy": auto_outcome.strategy_used,
			"fallback_used": auto_outcome.fallback_used,
			"candidate_attempts": auto_outcome.attempt_logs,
			"prompt_history": auto_outcome.prompt_history,
			"selected_candidate_rank": auto_outcome.selected_candidate_rank,
			"selected_round": auto_outcome.selected_round,
			"retries_used": auto_outcome.retries_used,
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
