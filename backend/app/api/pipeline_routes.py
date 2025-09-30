from __future__ import annotations

import uuid
import json
from http import HTTPStatus
from pathlib import Path
import shutil
import copy

from flask import Blueprint, current_app, jsonify, request
from werkzeug.datastructures import FileStorage

from ..models import PipelineRun, PipelineStage, QuestionManipulation
from ..services.pipeline.pipeline_orchestrator import PipelineConfig, PipelineOrchestrator
from ..services.pipeline.resume_service import PipelineResumeService
from ..services.pipeline.smart_substitution_service import SmartSubstitutionService
from ..services.data_management.file_manager import FileManager
from ..services.data_management.structured_data_manager import StructuredDataManager
from ..utils.exceptions import ResourceNotFound
from ..extensions import db
from ..utils.storage_paths import (
    pdf_input_path,
    run_directory,
    structured_data_path,
    assets_directory,
)


bp = Blueprint("pipeline", __name__, url_prefix="/pipeline")


def init_app(api_bp: Blueprint) -> None:
    api_bp.register_blueprint(bp)


@bp.post("/start")
def start_pipeline():
    orchestrator = PipelineOrchestrator()
    structured_manager = StructuredDataManager()
    structured_manager = StructuredDataManager()
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


@bp.get("/runs")
def list_runs():
    """List previous runs with optional filters.

    Query params:
      - q: search term (matches run id or filename)
      - status: comma-separated statuses to include
      - include_deleted: bool, include runs marked as soft-deleted in processing_stats.deleted
      - sort_by: one of created_at, updated_at, status, filename, validated_ratio
      - sort_dir: asc|desc
      - limit, offset
    """
    from sqlalchemy.orm import noload

    q = (request.args.get("q") or "").strip().lower()
    status_filter = set([s.strip().lower() for s in (request.args.get("status") or "").split(",") if s.strip()])
    include_deleted = (request.args.get("include_deleted") or "false").lower() == "true"
    sort_by = (request.args.get("sort_by") or "created_at").strip().lower()
    sort_dir = (request.args.get("sort_dir") or "desc").strip().lower()
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        limit, offset = 50, 0

    # Select only scalar columns and disable relationship loading to avoid coercion of legacy JSON rows
    base_query = (
        PipelineRun.query.options(
            noload(PipelineRun.stages),
            noload(PipelineRun.questions),
            noload(PipelineRun.enhanced_pdfs),
            noload(PipelineRun.logs),
            noload(PipelineRun.metrics),
            noload(PipelineRun.character_mappings),
            noload(PipelineRun.ai_model_results),
        )
        .with_entities(
            PipelineRun.id,
            PipelineRun.original_filename,
            PipelineRun.status,
            PipelineRun.current_stage,
            PipelineRun.created_at,
            PipelineRun.updated_at,
            PipelineRun.completed_at,
            PipelineRun.processing_stats,
            PipelineRun.structured_data,
        )
    )

    # Apply SQL-level sort where possible
    if sort_by in {"created_at", "updated_at", "status", "filename"}:
        if sort_by == "created_at":
            order_col = PipelineRun.created_at
        elif sort_by == "updated_at":
            order_col = PipelineRun.updated_at
        elif sort_by == "status":
            order_col = PipelineRun.status
        else:  # filename
            order_col = PipelineRun.original_filename
        base_query = base_query.order_by(order_col.desc() if sort_dir == "desc" else order_col.asc())
    else:
        # default order
        base_query = base_query.order_by(PipelineRun.created_at.desc())

    rows = base_query.all()

    items = []
    for row in rows:
        run_id = row[0]
        filename = row[1]
        status_val = row[2]
        current_stage = row[3]
        created_at = row[4]
        updated_at = row[5]
        completed_at = row[6]
        processing_stats = row[7] or {}
        structured = row[8] or {}

        deleted = bool(processing_stats.get("deleted"))
        if deleted and not include_deleted:
            continue
        if status_filter and (status_val or "").lower() not in status_filter:
            continue
        if q:
            hay = f"{run_id} {filename}".lower()
            if q not in hay:
                continue

        s_questions = structured.get("questions") or []
        total_questions = len(s_questions)
        validated_count = 0
        for qdict in s_questions:
            mappings = ((qdict.get("manipulation") or {}).get("substring_mappings")) or qdict.get("substring_mappings") or []
            if mappings and any(bool((m or {}).get("validated")) for m in mappings):
                validated_count += 1

        items.append(
            {
                "run_id": run_id,
                "filename": filename,
                "status": status_val,
                "current_stage": current_stage,
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "deleted": deleted,
                "total_questions": total_questions,
                "validated_count": validated_count,
            }
        )

    # In-memory sort for computed fields
    if sort_by == "validated_ratio":
        def ratio(it: dict) -> float:
            tq = max(1, int(it.get("total_questions") or 0))
            return (float(it.get("validated_count") or 0) / tq)
        items.sort(key=ratio, reverse=(sort_dir == "desc"))

    # Apply offset/limit after filtering
    total_count = len(items)
    items = items[offset: offset + limit]

    return jsonify({"runs": items, "count": total_count, "offset": offset, "limit": limit})


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


@bp.post("/<run_id>/continue")
def continue_pipeline(run_id: str):
    """Continue pipeline from current stage - typically used after paused_for_mapping status."""
    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    if run.status != "paused_for_mapping":
        return jsonify({"error": f"Cannot continue pipeline from status: {run.status}"}), HTTPStatus.BAD_REQUEST

    # Validate that questions have mappings
    questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
    if not questions:
        return jsonify({"error": "No questions found to continue pipeline"}), HTTPStatus.BAD_REQUEST

    # Check if at least some questions have mappings
    questions_with_mappings = [q for q in questions if q.substring_mappings]
    if not questions_with_mappings:
        return jsonify({"error": "At least one question must have mappings configured before continuing"}), HTTPStatus.BAD_REQUEST

    # Continue from smart_substitution to the end
    orchestrator = PipelineOrchestrator()
    remaining_stages = [
        "smart_substitution",
        "pdf_creation",
        "results_generation"
    ]

    config = PipelineConfig(
        target_stages=remaining_stages,
        ai_models=run.pipeline_config.get("ai_models", current_app.config["PIPELINE_DEFAULT_MODELS"]),
        enhancement_methods=run.pipeline_config.get(
            "enhancement_methods", current_app.config["PIPELINE_DEFAULT_METHODS"]
        ),
        skip_if_exists=False,
        parallel_processing=True,
    )

    orchestrator.start_background(run.id, config)

    return jsonify({
        "run_id": run.id,
        "status": "resumed",
        "continuing_stages": remaining_stages,
        "questions_with_mappings": len(questions_with_mappings),
        "total_questions": len(questions)
    })


@bp.post("/fork")
def fork_run():
    """Create a new run by forking from an existing run's data (up to smart_substitution).

    JSON body:
      - source_run_id: str
      - target_stages: optional list of stages to run for the new run (defaults to document_enhancement..end)
    """
    data = request.get_json(silent=True) or {}
    source_run_id = data.get("source_run_id")
    target_stages = data.get("target_stages") or []

    if not source_run_id:
        return jsonify({"error": "source_run_id required"}), HTTPStatus.BAD_REQUEST

    source = PipelineRun.query.get(source_run_id)
    if not source:
        return jsonify({"error": "Source run not found"}), HTTPStatus.NOT_FOUND

    # Create new run pointing to same original PDF, copy structured_data and questions
    new_id = str(uuid.uuid4())
    new_run = PipelineRun(
        id=new_id,
        original_pdf_path=source.original_pdf_path,
        original_filename=source.original_filename,
        current_stage="smart_substitution",
        status="pending",
        pipeline_config=source.pipeline_config or {},
        structured_data=source.structured_data or {},
    )
    db.session.add(new_run)
    db.session.flush()

    # Duplicate question rows including mappings and gold
    source_questions = QuestionManipulation.query.filter_by(pipeline_run_id=source_run_id).all()
    for q in source_questions:
        clone = QuestionManipulation(
            pipeline_run_id=new_id,
            question_number=q.question_number,
            question_type=q.question_type,
            original_text=q.original_text,
            stem_position=q.stem_position,
            options_data=q.options_data,
            gold_answer=q.gold_answer,
            gold_confidence=q.gold_confidence,
            manipulation_method=q.manipulation_method or "smart_substitution",
            substring_mappings=list(q.substring_mappings or []),
            effectiveness_score=q.effectiveness_score,
            ai_model_results=q.ai_model_results or {},
            visual_elements=q.visual_elements,
        )
        db.session.add(clone)

    db.session.commit()

    # Start new pipeline from requested stages (default: resume from document_enhancement onward)
    orchestrator = PipelineOrchestrator()
    if not target_stages:
        # Continue post-mapping stages by default
        target_stages = [
            stage.value
            for stage in orchestrator.pipeline_order
            if stage.value in ("document_enhancement", "pdf_creation", "results_generation")
        ]

    config = PipelineConfig(
        target_stages=target_stages,
        ai_models=new_run.pipeline_config.get("ai_models", current_app.config["PIPELINE_DEFAULT_MODELS"]),
        enhancement_methods=new_run.pipeline_config.get(
            "enhancement_methods", current_app.config["PIPELINE_DEFAULT_METHODS"]
        ),
        skip_if_exists=False,
        parallel_processing=True,
    )
    orchestrator.start_background(new_run.id, config)

    return jsonify({"run_id": new_run.id, "forked_from": source_run_id, "status": "started"}), HTTPStatus.ACCEPTED


@bp.post("/rerun")
def rerun_run():
    """Re-run from a previous run.

    Behavior:
    - If the source run has content discovery resources (questions/structured data), clone them and start at smart_substitution only.
    - Otherwise, create a fresh run that starts from the beginning (smart_reading..end).

    JSON body:
      - source_run_id: str
      - target_stages: optional override list
    """
    data = request.get_json(silent=True) or {}
    source_run_id = data.get("source_run_id")
    target_stages = data.get("target_stages") or None

    if not source_run_id:
        return jsonify({"error": "source_run_id required"}), HTTPStatus.BAD_REQUEST

    source = PipelineRun.query.get(source_run_id)
    if not source:
        return jsonify({"error": "Source run not found"}), HTTPStatus.NOT_FOUND

    orchestrator = PipelineOrchestrator()
    structured_manager = StructuredDataManager()

    # Determine readiness: consider either DB questions, structured questions, or AI questions
    structured = source.structured_data or {}
    s_questions = structured.get("questions") or []
    s_ai_questions = structured.get("ai_questions") or []
    has_db_questions = bool(QuestionManipulation.query.filter_by(pipeline_run_id=source_run_id).first())
    ready_for_clone = bool(s_questions) or bool(s_ai_questions) or has_db_questions

    if ready_for_clone:
        # Clone as a new run prepped for smart_substitution
        new_id = str(uuid.uuid4())

        # Prepare run directory and replicate upstream assets
        run_directory(new_id)
        source_run_dir = run_directory(source_run_id)

        # Copy original PDF into the new run directory if available
        dest_pdf_path: Path | None = None
        source_pdf_path = Path(source.original_pdf_path) if source.original_pdf_path else None
        if source_pdf_path and source_pdf_path.exists():
            dest_pdf_path = pdf_input_path(new_id, source_pdf_path.name)
            dest_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_pdf_path, dest_pdf_path)

        # Copy assets (images, fonts, etc.) for downstream renderers
        source_assets_dir = source_run_dir / "assets"
        if source_assets_dir.exists():
            dest_assets_dir = assets_directory(new_id)
            shutil.rmtree(dest_assets_dir, ignore_errors=True)
            shutil.copytree(source_assets_dir, dest_assets_dir, dirs_exist_ok=True)

        structured_copy = copy.deepcopy(structured or {})
        document_info = structured_copy.setdefault("document", {})
        if dest_pdf_path:
            document_info["source_path"] = str(dest_pdf_path)
            document_info.setdefault("filename", dest_pdf_path.name)
        elif source_pdf_path:
            document_info.setdefault("source_path", str(source_pdf_path))
            document_info.setdefault("filename", source_pdf_path.name)

        metadata = structured_copy.setdefault("pipeline_metadata", {})
        stages_completed = set(metadata.get("stages_completed") or [])
        stages_completed.update({"smart_reading", "content_discovery"})
        metadata["stages_completed"] = sorted(stages_completed)
        metadata["current_stage"] = "smart_substitution"

        # Persist structured copy on disk for the cloned run
        structured_manager.save(new_id, structured_copy)

        pdf_path_for_run = dest_pdf_path or source_pdf_path

        new_run = PipelineRun(
            id=new_id,
            original_pdf_path=str(pdf_path_for_run) if pdf_path_for_run else source.original_pdf_path,
            original_filename=(pdf_path_for_run.name if pdf_path_for_run else source.original_filename),
            current_stage="smart_substitution",
            status="pending",
            pipeline_config=copy.deepcopy(source.pipeline_config or {}),
            structured_data=structured_copy,
        )
        db.session.add(new_run)
        db.session.flush()

        # Duplicate questions if present in DB; otherwise synthesize from AI questions
        source_questions = QuestionManipulation.query.filter_by(pipeline_run_id=source_run_id).all()
        if source_questions:
            for q in source_questions:
                clone = QuestionManipulation(
                    pipeline_run_id=new_id,
                    question_number=q.question_number,
                    question_type=q.question_type,
                    original_text=q.original_text,
                    stem_position=q.stem_position,
                    options_data=q.options_data,
                    gold_answer=q.gold_answer,
                    gold_confidence=q.gold_confidence,
                    manipulation_method=q.manipulation_method or "smart_substitution",
                    # Do not assign substring_mappings here to avoid MutableList coercion; UI/API will manage
                    effectiveness_score=q.effectiveness_score,
                    ai_model_results=q.ai_model_results or {},
                    visual_elements=q.visual_elements,
                )
                mappings_copy = json.loads(json.dumps(q.substring_mappings or []))
                clone.substring_mappings = mappings_copy
                db.session.add(clone)
        else:
            # Seed minimal QuestionManipulation rows from structured AI questions
            for aq in (s_ai_questions or []):
                qnum = str(aq.get("question_number") or aq.get("q_number") or "")
                if not qnum:
                    continue
                clone = QuestionManipulation(
                    pipeline_run_id=new_id,
                    question_number=qnum,
                    question_type=str(aq.get("question_type") or "multiple_choice"),
                    original_text=str(aq.get("stem_text") or ""),
                    options_data=aq.get("options") or {},
                    manipulation_method="smart_substitution",
                    # Do not assign substring_mappings here to avoid MutableList coercion; UI/API will manage
                    ai_model_results={},
                )
                db.session.add(clone)

        db.session.commit()

        # Verify mappings were copied correctly
        cloned_count = QuestionManipulation.query.filter_by(pipeline_run_id=new_id).count()
        cloned_with_mappings = db.session.query(QuestionManipulation).filter(
            QuestionManipulation.pipeline_run_id == new_id,
            QuestionManipulation.substring_mappings != None,
            QuestionManipulation.substring_mappings != '[]'
        ).count()

        # Ensure structured data mirrors the cloned DB rows (including substring mappings)
        SmartSubstitutionService().sync_structured_mappings(new_id)
        new_run.structured_data = structured_manager.load(new_id)
        db.session.commit()

        # Default to only smart_substitution (UI will carry forward after mappings are validated)
        default_stages = ["smart_substitution"]
        stages = target_stages if target_stages else default_stages
        config = PipelineConfig(
            target_stages=stages,
            ai_models=new_run.pipeline_config.get("ai_models", current_app.config["PIPELINE_DEFAULT_MODELS"]),
            enhancement_methods=new_run.pipeline_config.get(
                "enhancement_methods", current_app.config["PIPELINE_DEFAULT_METHODS"]
            ),
            skip_if_exists=False,
            parallel_processing=True,
        )
        orchestrator.start_background(new_run.id, config)

        return jsonify({"run_id": new_run.id, "rerun_from": source_run_id, "mode": "clone_ready", "status": "started"}), HTTPStatus.ACCEPTED

    # Otherwise, start a fresh run from the beginning using the same PDF
    new_id = str(uuid.uuid4())
    source_pdf = Path(source.original_pdf_path)
    dest_pdf = pdf_input_path(new_id, source_pdf.name)
    dest_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_pdf, dest_pdf)

    new_run = PipelineRun(
        id=new_id,
        original_pdf_path=str(dest_pdf),
        original_filename=source_pdf.name,
        current_stage="smart_reading",
        status="pending",
        pipeline_config=source.pipeline_config or {},
        structured_data={},
    )
    db.session.add(new_run)
    db.session.commit()

    # Initialize structured data file with the input PDF (now copied into new run dir)
    StructuredDataManager().initialize(new_run.id, dest_pdf)

    # Run full pipeline by default
    config = PipelineConfig(
        target_stages=[stage.value for stage in orchestrator.pipeline_order],
        ai_models=new_run.pipeline_config.get("ai_models", current_app.config["PIPELINE_DEFAULT_MODELS"]),
        enhancement_methods=new_run.pipeline_config.get(
            "enhancement_methods", current_app.config["PIPELINE_DEFAULT_METHODS"]
        ),
        skip_if_exists=False,
        parallel_processing=True,
    )
    orchestrator.start_background(new_run.id, config)

    return jsonify({"run_id": new_run.id, "rerun_from": source_run_id, "mode": "fresh_start", "status": "started"}), HTTPStatus.ACCEPTED


@bp.post("/<run_id>/soft_delete")
def soft_delete_run(run_id: str):
    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    stats = run.processing_stats or {}
    stats["deleted"] = True
    run.processing_stats = stats
    db.session.add(run)
    db.session.commit()

    return jsonify({"run_id": run.id, "deleted": True})


@bp.delete("/<run_id>")
def delete_run(run_id: str):
    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    FileManager().delete_run_artifacts(run_id)
    db.session.delete(run)
    db.session.commit()

    return "", HTTPStatus.NO_CONTENT
