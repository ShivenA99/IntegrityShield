from __future__ import annotations

import uuid
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request
from werkzeug.datastructures import FileStorage

from ..models import PipelineRun, PipelineStage
from ..services.pipeline.pipeline_orchestrator import PipelineConfig, PipelineOrchestrator
from ..services.pipeline.resume_service import PipelineResumeService
from ..services.data_management.file_manager import FileManager
from ..services.data_management.structured_data_manager import StructuredDataManager
from ..utils.exceptions import ResourceNotFound
from ..extensions import db


bp = Blueprint("pipeline", __name__, url_prefix="/pipeline")


def init_app(api_bp: Blueprint) -> None:
    api_bp.register_blueprint(bp)


@bp.post("/start")
def start_pipeline():
    orchestrator = PipelineOrchestrator()
    file_manager = FileManager()
    structured_manager = StructuredDataManager()

    resume_from_run_id = request.form.get("resume_from_run_id")
    target_stages = request.form.getlist("target_stages") or []
    ai_models = request.form.getlist("ai_models") or current_app.config["PIPELINE_DEFAULT_MODELS"]
    enhancement_methods = request.form.getlist("enhancement_methods") or current_app.config[
        "PIPELINE_DEFAULT_METHODS"
    ]
    skip_if_exists = request.form.get("skip_if_exists", "true").lower() == "true"
    parallel_processing = request.form.get("parallel_processing", "true").lower() == "true"
    mapping_strategy = request.form.get("mapping_strategy", "unicode_steganography")

    uploaded_file: FileStorage | None = request.files.get("original_pdf")
    if not resume_from_run_id and not uploaded_file:
        return jsonify({"error": "original_pdf file required"}), HTTPStatus.BAD_REQUEST

    if resume_from_run_id:
        run = PipelineRun.query.get(resume_from_run_id)
        if not run:
            return jsonify({"error": "Invalid resume_from_run_id"}), HTTPStatus.NOT_FOUND
    else:
        if not uploaded_file:
            return jsonify({"error": "original_pdf file required"}), HTTPStatus.BAD_REQUEST

        run_id = str(uuid.uuid4())
        pdf_path = file_manager.save_uploaded_pdf(run_id, uploaded_file)

        run = PipelineRun(
            id=run_id,
            original_pdf_path=str(pdf_path),
            original_filename=uploaded_file.filename or "uploaded.pdf",
            current_stage="smart_reading",
            status="pending",
            pipeline_config={
                "ai_models": ai_models,
                "enhancement_methods": enhancement_methods,
            },
            structured_data={},
        )
        db.session.add(run)
        db.session.commit()

        structured_manager.initialize(run.id, pdf_path)

    config = PipelineConfig(
        target_stages=target_stages or [stage.value for stage in orchestrator.pipeline_order],
        ai_models=ai_models,
        enhancement_methods=enhancement_methods,
        skip_if_exists=skip_if_exists,
        parallel_processing=parallel_processing,
        mapping_strategy=mapping_strategy,
    )

    orchestrator.start_background(run.id, config)

    return (
        jsonify(
            {
                "run_id": run.id,
                "status": "started",
                "config": config.to_dict(),
            }
        ),
        HTTPStatus.ACCEPTED,
    )


@bp.get("/<run_id>/status")
def get_status(run_id: str):
    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    stages = PipelineStage.query.filter_by(pipeline_run_id=run_id).order_by(PipelineStage.id).all()

    return jsonify(
        {
            "run_id": run.id,
            "status": run.status,
            "current_stage": run.current_stage,
            "stages": [
                {
                    "id": stage.id,
                    "name": stage.stage_name,
                    "status": stage.status,
                    "duration_ms": stage.duration_ms,
                    "error": stage.error_details,
                }
                for stage in stages
            ],
            "processing_stats": run.processing_stats,
            "pipeline_config": run.pipeline_config,
            "structured_data": run.structured_data,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }
    )


@bp.post("/<run_id>/resume/<stage_name>")
def resume_pipeline(run_id: str, stage_name: str):
    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    resume_service = PipelineResumeService()
    try:
        resume_service.mark_for_resume(run_id, stage_name)
    except ResourceNotFound as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

    config = PipelineConfig(
        target_stages=[stage_name],
        ai_models=run.pipeline_config.get("ai_models", current_app.config["PIPELINE_DEFAULT_MODELS"]),
        enhancement_methods=run.pipeline_config.get(
            "enhancement_methods", current_app.config["PIPELINE_DEFAULT_METHODS"]
        ),
        skip_if_exists=False,
        parallel_processing=True,
    )

    orchestrator = PipelineOrchestrator()
    orchestrator.start_background(run.id, config)

    return jsonify({"run_id": run.id, "resumed_from": stage_name, "status": "resumed"})


@bp.delete("/<run_id>")
def delete_run(run_id: str):
    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    FileManager().delete_run_artifacts(run_id)
    db.session.delete(run)
    db.session.commit()

    return "", HTTPStatus.NO_CONTENT
