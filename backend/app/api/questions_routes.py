from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request
import json
from sqlalchemy import text

from ..extensions import db
from ..models import AIModelResult, PipelineRun, QuestionManipulation
from ..services.intelligence.multi_model_tester import MultiModelTester
from ..services.pipeline.smart_substitution_service import SmartSubstitutionService
from ..services.integration.external_api_client import ExternalAIClient
from ..services.manipulation.substring_manipulator import SubstringManipulator
from ..services.validation.gpt5_validation_service import GPT5ValidationService
from ..utils.exceptions import ResourceNotFound


bp = Blueprint("questions", __name__, url_prefix="/questions")


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
					"manipulation_method": question.manipulation_method,
					"effectiveness_score": question.effectiveness_score,
					"substring_mappings": question.substring_mappings or [],
					"ai_model_results": question.ai_model_results or {},
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


@bp.put("/<run_id>/<question_id>/manipulation")
def update_manipulation(run_id: str, question_id: int):
	question = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
	if not question:
		return jsonify({"error": "Question manipulation not found"}), HTTPStatus.NOT_FOUND

	payload = request.json or {}
	method = payload.get("method")
	substring_mappings = payload.get("substring_mappings", [])
	custom_mappings = payload.get("custom_mappings")

	question.manipulation_method = method
	# Use raw SQL to bypass mutable tracking issues
	db.session.execute(
		text("UPDATE question_manipulations SET substring_mappings = :mappings WHERE id = :id"),
		{"mappings": json.dumps(substring_mappings), "id": question.id}
	)
	if custom_mappings:
		question.ai_model_results = question.ai_model_results or {}
		question.ai_model_results["custom_mappings"] = custom_mappings

	db.session.add(question)
	db.session.commit()
	SmartSubstitutionService().sync_structured_mappings(run_id)

	if payload.get("regenerate_mappings"):
		SmartSubstitutionService().refresh_question_mapping(run_id, question.question_number)

	return jsonify({"status": "updated", "question_id": question.id, "method": method})


@bp.post("/<run_id>/<question_id>/validate")
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
	model = payload.get("model", "openai:gpt-4o-mini")
	validated_mapping_id = payload.get("mapping_id")

	# Step 1: Apply mappings to create modified question
	manipulator = SubstringManipulator()
	try:
		# Use structured ai_questions stem_text if present; fallback to original_text
		structured = StructuredDataManager().load(run_id)
		ai_map = {str(q.get("question_number", q.get("q_number", ""))): q for q in structured.get("ai_questions", [])}
		rich = ai_map.get(str(question.question_number), {})
		source_text = rich.get("stem_text") or question.original_text or ""
		modified = manipulator.apply_mappings_to_text(source_text, mappings)
	except ValueError as exc:
		return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

	# Step 2: Get model response to modified question
	prompt = f"Question: {modified}\n"
	if question.options_data:
		prompt += "Options:\n"
		for k, v in (question.options_data or {}).items():
			prompt += f"{k}. {v}\n"
	prompt += "\nReturn only the final answer (e.g., option letter or short text)."

	client = ExternalAIClient()
	result = client.call_model(provider=model, payload={"prompt": prompt})
	test_answer = (result or {}).get("response", "").strip()

	# Step 3: Use GPT-5 to intelligently validate the answer deviation
	validator = GPT5ValidationService()
	validation_result = validator.validate_answer_deviation(
		question_text=modified,
		question_type=question.question_type or "mcq_single",
		gold_answer=question.gold_answer or "",
		test_answer=test_answer,
		options_data=question.options_data,
		run_id=run_id,
	)

	# Step 4: Create comprehensive validation record
	validation_record = {
		"model": model,
		"response": test_answer,
		"gold": question.gold_answer,
		"prompt_len": len(prompt),
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
	question.ai_model_results["last_validation"] = validation_record

	# Update specific mapping if mapping_id provided
	if validated_mapping_id and question.substring_mappings:
		for m in question.substring_mappings:
			if str(m.get("id")) == str(validated_mapping_id):
				m["validation"] = validation_record
				m["validated"] = validation_result.is_valid
				m["confidence"] = validation_result.confidence
				m["deviation_score"] = validation_result.deviation_score
				break
		# ensure ORM sees mutation
		db.session.add(question)

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


@bp.post("/<run_id>/<question_id>/test")
def test_question(run_id: str, question_id: int):
	tester = MultiModelTester()
	payload = request.json or {}
	models = payload.get("models")

	try:
		results = tester.test_question(run_id, question_id, models=models)
	except ResourceNotFound as exc:
		return jsonify({"error": str(exc)}), HTTPStatus.NOT_FOUND

	return jsonify(results)


@bp.get("/<run_id>/<question_id>/history")
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

	updated_count = 0
	errors = []

	for question_data in questions_data:
		question_id = question_data.get("id")
		substring_mappings = question_data.get("substring_mappings", [])
		manipulation_method = question_data.get("manipulation_method", "smart_substitution")

		question = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
		if not question:
			errors.append(f"Question {question_id} not found")
			continue

		try:
			question.manipulation_method = manipulation_method
			# Use raw SQL to bypass mutable tracking issues with JSONB
			db.session.execute(
				text("UPDATE question_manipulations SET substring_mappings = :mappings WHERE id = :id"),
				{"mappings": json.dumps(substring_mappings), "id": question.id}
			)
			db.session.add(question)
			updated_count += 1
		except Exception as e:
			errors.append(f"Question {question_id}: {str(e)}")

	try:
		db.session.commit()
	except Exception as e:
		db.session.rollback()
		return jsonify({"error": f"Failed to save mappings: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR

	SmartSubstitutionService().sync_structured_mappings(run_id)

	result = {
		"run_id": run_id,
		"updated_count": updated_count,
		"total_questions": len(questions_data)
	}

	if errors:
		result["errors"] = errors

	return jsonify(result)
