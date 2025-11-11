import json

import pytest

from app import create_app
from app.extensions import db
from app.models import QuestionManipulation
from app.services.pipeline.content_discovery_service import ContentDiscoveryService
from app.services.data_management.structured_data_manager import StructuredDataManager
from app.utils.storage_paths import run_directory


@pytest.fixture
def app_context(tmp_path):
	app = create_app("testing")
	app.config["PIPELINE_STORAGE_ROOT"] = tmp_path / "runs"
	with app.app_context():
		db.create_all()
		yield app
		db.session.remove()
		db.drop_all()


def _build_ai_question(number: str, stem: str, question_id: str) -> dict:
	return {
		"question_number": number,
		"stem_text": stem,
		"options": {
			"A": f"{stem} option A",
			"B": f"{stem} option B",
		},
		"positioning": {
			"page": 1,
			"bbox": [0, 0, 100, 20],
			"stem_spans": [f"span-{question_id}"],
		},
		"question_id": question_id,
		"metadata": {"section": "duplicate"},
	}


def test_content_discovery_preserves_order_with_duplicate_numbers(app_context):
	run_id = "dup-questions"
	run_directory(run_id)
	manager = StructuredDataManager()

	structured = {
		"pipeline_metadata": {"current_stage": "smart_reading", "stages_completed": []},
		"ai_questions": [
			_build_ai_question("1", "First stem", "q-1a"),
			_build_ai_question("1", "Second stem", "q-1b"),
		],
	}
	manager.save(run_id, structured)

	service = ContentDiscoveryService()
	service._discover_questions(run_id)

	questions = (
		QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
		.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
		.all()
	)
	assert len(questions) == 2
	assert [q.sequence_index for q in questions] == [0, 1]
	assert [q.source_identifier for q in questions] == ["q-1a", "q-1b"]

	loaded = manager.load(run_id)
	structured_questions = loaded.get("questions", [])
	assert len(structured_questions) == 2
	assert [entry.get("manipulation_id") for entry in structured_questions] == [questions[0].id, questions[1].id]
	assert [entry.get("sequence_index") for entry in structured_questions] == [0, 1]

	# Simulate validated mapping to enable preservation branch
	questions[0].substring_mappings = [{"id": "m1", "original": "First", "replacement": "Third"}]
	db.session.add(questions[0])
	db.session.commit()

	loaded["pipeline_metadata"]["stages_completed"] = ["smart_substitution"]
	manager.save(run_id, loaded)

	service._discover_questions(run_id)
	questions_after = (
		QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
		.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
		.all()
	)
	assert [q.id for q in questions_after] == [questions[0].id, questions[1].id]
	assert [q.sequence_index for q in questions_after] == [0, 1]





