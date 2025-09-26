from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request
import json

from ..extensions import db
from ..models import AIModelResult, PipelineRun, QuestionManipulation
from ..services.intelligence.multi_model_tester import MultiModelTester
from ..services.pipeline.smart_substitution_service import SmartSubstitutionService
from ..services.integration.external_api_client import ExternalAIClient
from ..services.manipulation.substring_manipulator import SubstringManipulator
from ..utils.exceptions import ResourceNotFound


bp = Blueprint("questions", __name__, url_prefix="/questions")


def init_app(api_bp: Blueprint) -> None:
	api_bp.register_blueprint(bp)


@bp.get("/<run_id>")
def list_questions(run_id: str):
	run = PipelineRun.query.get(run_id)
	if not run:
		return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

	questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()

	return jsonify(
		{
			"run_id": run.id,
			"questions": [
				{
					"id": question.id,
					"question_number": question.question_number,
					"question_type": question.question_type,
					"original_text": question.original_text,
					"options_data": question.options_data,
					"gold_answer": question.gold_answer,
					"manipulation_method": question.manipulation_method,
					"effectiveness_score": question.effectiveness_score,
					"substring_mappings": question.substring_mappings,
					"ai_model_results": question.ai_model_results,
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
	# deep-coerce and mutate in place for MutableList compatibility
	json_safe = json.loads(json.dumps(substring_mappings))
	if question.substring_mappings is None:
		question.substring_mappings = []
	else:
		question.substring_mappings.clear()
	question.substring_mappings.extend(json_safe)
	if custom_mappings:
		question.ai_model_results["custom_mappings"] = custom_mappings

	db.session.add(question)
	db.session.commit()

	if payload.get("regenerate_mappings"):
		SmartSubstitutionService().refresh_question_mapping(run_id, question.question_number)

	return jsonify({"status": "updated", "question_id": question.id, "method": method})


@bp.post("/<run_id>/<question_id>/validate")
def validate_mapping(run_id: str, question_id: int):
	"""Apply provided substring_mappings to the stem and ask a model for the answer.
	Returns the model's answer so the UI can compare to gold_answer.
	Also stores a lightweight validation record in ai_model_results.last_validation.
	"""
	question = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
	if not question:
		return jsonify({"error": "Question manipulation not found"}), HTTPStatus.NOT_FOUND

	payload = request.json or {}
	mappings = payload.get("substring_mappings", [])
	model = payload.get("model", "openai:gpt-4o-mini")
	validated_mapping_id = payload.get("mapping_id")

	manipulator = SubstringManipulator()
	try:
		modified = manipulator.apply_mappings_to_text(question.original_text or "", mappings)
	except ValueError as exc:
		return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

	# Build a simple prompt based on question_type; for MCQ include options
	prompt = f"Question: {modified}\n"
	if question.options_data:
		prompt += "Options:\n"
		for k, v in (question.options_data or {}).items():
			prompt += f"{k}. {v}\n"
	prompt += "\nReturn only the final answer (e.g., option letter or short text)."

	client = ExternalAIClient()
	result = client.call_model(provider=model, payload={"prompt": prompt})

	# Persist a minimal validation record
	validation_record = {
		"model": model,
		"response": result.get("response"),
		"gold": question.gold_answer,
		"prompt_len": len(prompt),
	}
	question.ai_model_results = question.ai_model_results or {}
	question.ai_model_results["last_validation"] = validation_record

	# Also persist onto a specific mapping entry if mapping_id provided
	if validated_mapping_id and question.substring_mappings:
		for m in question.substring_mappings:
			if str(m.get("id")) == str(validated_mapping_id):
				m["validation"] = validation_record
				m["validated"] = bool(result.get("response")) and (question.gold_answer is None or str(result.get("response")).strip() == str(question.gold_answer).strip())
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
