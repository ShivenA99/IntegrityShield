import json
from types import SimpleNamespace

import pytest

from app import create_app
from app.extensions import db
from app.models import QuestionManipulation
from app.services.mapping.mapping_staging_service import MappingStagingService
from app.services.pipeline.smart_substitution_service import SmartSubstitutionService
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


def test_mapping_staging_records_variants(app_context):
    service = MappingStagingService()
    run_id = "run-staging"
    question = SimpleNamespace(id=1, question_number="1")

    mapping_payload = {
        "original_substring": "Mercury",
        "replacement_substring": "Mars",
        "start_pos": 0,
        "end_pos": 7,
        "latex_stem_text": "Mercury is the smallest planet.",
    }
    logs = [
        {
            "status": "success",
            "validation_result": {"confidence": 0.92, "deviation_score": 0.81, "reasoning": "Target flips to B"},
        }
    ]

    service.stage_valid_mapping(run_id, question, mapping_payload, generated_count=3, validation_logs=logs, metadata={"job_id": "job-1", "strategy": "replacement"})

    data = service.load(run_id)
    assert data["run_id"] == run_id
    entry = data["questions"]["1"]
    assert entry["status"] == "validated"
    assert entry["validation_summary"]["confidence"] == pytest.approx(0.92)
    assert entry["staged_mapping"]["replacement"] == "Mars"
    assert entry["staged_mapping"]["start_pos"] == 0

    # Stage a skip and a failure to ensure entries overwrite correctly
    service.stage_no_valid_mapping(run_id, question, generated_count=2, validation_logs=[], metadata={"job_id": "job-2", "skip_reason": "No candidate caused deviation"})
    service.stage_failure(run_id, question, "model timeout", metadata={"job_id": "job-3"})

    data = service.load(run_id)
    entry = data["questions"]["1"]
    assert entry["status"] == "failed"
    assert entry["error"] == "model timeout"


def test_promote_staged_mappings_updates_questions(app_context):
    run_id = "run-promote"
    run_directory(run_id)  # ensure run path exists
    staging = MappingStagingService()
    service = SmartSubstitutionService()

    q1 = QuestionManipulation(
        pipeline_run_id=run_id,
        question_number="1",
        question_type="mcq_single",
        original_text="Mercury is the smallest planet.",
		options_data={"A": "Mercury", "B": "Mars"},
		sequence_index=0,
		source_identifier="test-q1",
    )
    q2 = QuestionManipulation(
        pipeline_run_id=run_id,
        question_number="2",
        question_type="true_false",
        original_text="The Sun is a planet.",
		options_data={"True": "True", "False": "False"},
		sequence_index=1,
		source_identifier="test-q2",
    )
    db.session.add_all([q1, q2])
    db.session.commit()

    staging.stage_valid_mapping(
        run_id,
        q1,
        {
            "original_substring": "Mercury",
            "replacement_substring": "Mars",
            "start_pos": 0,
            "end_pos": 7,
            "latex_stem_text": "Mercury is the smallest planet.",
        },
        generated_count=3,
        validation_logs=[{"status": "success", "validation_result": {"confidence": 0.85, "deviation_score": 0.74}}],
        metadata={"job_id": "job-q1", "strategy": "replacement"},
    )

    staging.stage_no_valid_mapping(
        run_id,
        q2,
        generated_count=3,
        validation_logs=[{"status": "failed"}],
        metadata={"job_id": "job-q2", "skip_reason": "All candidates preserved answer"},
    )

    summary = service.promote_staged_mappings(run_id)
    assert summary["promoted"] == ["1"]
    assert any(entry["question_number"] == "2" for entry in summary["skipped"])

    updated_q1 = QuestionManipulation.query.get(q1.id)
    assert updated_q1.substring_mappings
    assert updated_q1.substring_mappings[0]["replacement"] == "Mars"
    assert updated_q1.manipulation_method == "gpt5_generated"

    structured_path = run_directory(run_id) / "structured.json"
    data = json.loads(structured_path.read_text(encoding="utf-8"))
    assert data["manipulation_results"]["staged_promoted_questions"] == ["1"]
    assert any(entry["question_number"] == "2" for entry in data["manipulation_results"]["staged_skipped_questions"])
