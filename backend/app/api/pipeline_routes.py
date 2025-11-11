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
from ..services.pipeline.pipeline_orchestrator import (
    PipelineConfig,
    PipelineOrchestrator,
    PipelineStageEnum,
)
from ..services.pipeline.resume_service import PipelineResumeService
from ..services.pipeline.smart_substitution_service import SmartSubstitutionService
from ..services.data_management.file_manager import FileManager
from ..services.data_management.structured_data_manager import StructuredDataManager
from ..services.pipeline.manual_input_loader import ManualInputLoader
from ..utils.exceptions import ResourceNotFound
from ..extensions import db
from ..utils.storage_paths import (
    pdf_input_path,
    run_directory,
    assets_directory,
)
from ..utils.time import isoformat, utc_now


bp = Blueprint("pipeline", __name__, url_prefix="/pipeline")


def init_app(api_bp: Blueprint) -> None:
    api_bp.register_blueprint(bp)


@bp.post("/start")
def start_pipeline():
    orchestrator = PipelineOrchestrator()
    structured_manager = StructuredDataManager()
    file_manager = FileManager()

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
    manual_mode = not resume_from_run_id and not uploaded_file

    if manual_mode:
        manual_dir: Path = current_app.config.get("MANUAL_INPUT_DIR")
        loader = ManualInputLoader(Path(manual_dir))
        try:
            payload = loader.build()
        except (FileNotFoundError, FileExistsError, ValueError) as exc:
            return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

        run_id = str(uuid.uuid4())
        destination_pdf = file_manager.import_manual_pdf(run_id, payload.pdf_path)

        structured = copy.deepcopy(payload.structured_data)
        metadata = structured.setdefault("pipeline_metadata", {})
        metadata.update(
            {
                "run_id": run_id,
                "current_stage": PipelineStageEnum.RESULTS_GENERATION.value,
                "stages_completed": [stage.value for stage in PipelineStageEnum],
                "last_updated": isoformat(utc_now()),
                "manual_input": True,
            }
        )
        metadata["manual_source_paths"] = payload.source_paths
        metadata["manual_input_overrides"] = [
            PipelineStageEnum.SMART_READING.value,
            PipelineStageEnum.CONTENT_DISCOVERY.value,
        ]

        structured_document = structured.setdefault("document", {})
        structured["document"]["source_path"] = str(destination_pdf)
        structured["document"]["filename"] = destination_pdf.name
        structured_document["pipeline_pdf_path"] = str(destination_pdf)

        structured_manual = structured.setdefault("manual_input", {})
        structured_manual["pipeline_pdf_path"] = str(destination_pdf)
        structured_manual["source_paths"] = payload.source_paths

        default_display_page = 1
        for collection_name in ("ai_questions", "questions"):
            for question_entry in structured.get(collection_name, []) or []:
                positioning = question_entry.setdefault("positioning", {})
                if positioning.get("page") is None:
                    positioning["page"] = default_display_page

        for index_entry in structured.get("question_index", []) or []:
            if index_entry.get("page") is None:
                index_entry["page"] = default_display_page
            positioning = index_entry.get("positioning")
            if isinstance(positioning, dict) and positioning.get("page") is None:
                positioning["page"] = default_display_page

        doc_meta = payload.doc_metadata
        run = PipelineRun(
            id=run_id,
            original_pdf_path=str(destination_pdf),
            original_filename=destination_pdf.name,
            current_stage=PipelineStageEnum.RESULTS_GENERATION.value,
            status="completed",
            pipeline_config={
                "ai_models": ai_models,
                "enhancement_methods": enhancement_methods,
                "skip_if_exists": skip_if_exists,
                "parallel_processing": parallel_processing,
                "mapping_strategy": mapping_strategy,
                "manual_input": True,
                "manual_source_paths": payload.source_paths,
            },
            processing_stats={
                "manual_input": True,
                "question_count": len(payload.questions),
                "document_name": doc_meta.get("document_name"),
                "subjects": doc_meta.get("subjects"),
                "domain": doc_meta.get("domain"),
                "generated_at": doc_meta.get("generated_at"),
            },
            structured_data=structured,
        )

        db.session.add(run)
        db.session.flush()

        now = utc_now()
        stage_payload = {
            "mode": "manual_seed",
            "generated_at": isoformat(now),
        }
        for stage_enum in PipelineStageEnum:
            stage_record = PipelineStage(
                pipeline_run_id=run_id,
                stage_name=stage_enum.value,
                status="completed",
                stage_data=stage_payload,
                duration_ms=0,
                started_at=now,
                completed_at=now,
            )
            db.session.add(stage_record)

        for idx, question in enumerate(payload.questions):
            ai_results_meta = {
                "manual_seed": {
                    "marks": question.marks,
                    "explanation": question.explanation,
                    "source_dataset": question.source_dataset,
                    "source_id": question.source_id,
                    "question_id": question.question_id,
                    "gold_confidence": question.gold_confidence,
                    "has_image": question.has_image,
                    "image_path": question.image_path,
                }
            }
            gold_confidence = (
                question.gold_confidence
                if question.gold_confidence is not None
                else (1.0 if question.gold_answer else None)
            )
            visual_elements = None
            if question.image_path:
                visual_elements = [
                    {
                        "type": "image",
                        "path": question.image_path,
                        "source": "manual_input",
                    }
                ]
            question_model = QuestionManipulation(
                pipeline_run_id=run_id,
                question_number=str(question.number),
                question_type=question.question_type,
                original_text=question.stem_text,
                options_data=question.options,
                gold_answer=question.gold_answer,
                gold_confidence=gold_confidence,
                sequence_index=idx,
                source_identifier=str(
                    question.source_id
                    or question.question_id
                    or question.number
                    or f"manual-{idx}"
                ),
                manipulation_method="manual_seed",
                ai_model_results=ai_results_meta,
                substring_mappings=[],
                visual_elements=visual_elements,
            )
            question_model.stem_position = {"page": 0, "bbox": None}
            db.session.add(question_model)

        db.session.commit()
        structured_manager.save(run_id, structured)

        return (
            jsonify(
                {
                    "run_id": run_id,
                    "status": "completed",
                    "config": {
                        "manual_input": True,
                        "question_count": len(payload.questions),
                    },
                }
            ),
            HTTPStatus.ACCEPTED,
        )

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

    target_stages = [stage_name]
    promotion_summary: Dict[str, Any] = {"promoted": [], "skipped": [], "total_promoted": 0}
    if stage_name == PipelineStageEnum.PDF_CREATION.value:
        questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
        if not questions:
            return jsonify({"error": "No questions available for PDF creation"}), HTTPStatus.BAD_REQUEST

        smart_service = SmartSubstitutionService()
        try:
            promotion_summary = smart_service.promote_staged_mappings(run_id)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), HTTPStatus.CONFLICT
        smart_service.sync_structured_mappings(run_id)
        current_app.logger.info(
            "Pre-PDF staging sync completed",
            extra={
                "run_id": run_id,
                "promoted_mappings": promotion_summary.get("promoted"),
                "skipped_mappings": promotion_summary.get("skipped"),
            },
        )
        target_stages.append(PipelineStageEnum.RESULTS_GENERATION.value)

    config = PipelineConfig(
        target_stages=target_stages,
        ai_models=run.pipeline_config.get("ai_models", current_app.config["PIPELINE_DEFAULT_MODELS"]),
        enhancement_methods=run.pipeline_config.get(
            "enhancement_methods", current_app.config["PIPELINE_DEFAULT_METHODS"]
        ),
        skip_if_exists=False,
        parallel_processing=True,
    )

    orchestrator = PipelineOrchestrator()
    orchestrator.start_background(run.id, config)

    return jsonify(
        {
            "run_id": run.id,
            "resumed_from": stage_name,
            "status": "resumed",
            "promotion_summary": promotion_summary,
        }
    )


@bp.post("/<run_id>/continue")
def continue_pipeline(run_id: str):
    """Resume downstream stages for a run once mappings are ready."""
    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    if run.status == "running":
        return jsonify({"error": "Pipeline is already running"}), HTTPStatus.BAD_REQUEST

    # Validate that questions have mappings
    questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
    if not questions:
        return jsonify({"error": "No questions found to continue pipeline"}), HTTPStatus.BAD_REQUEST

    missing = [q.question_number for q in questions if not (q.substring_mappings or [])]
    if missing:
        return (
            jsonify(
                {
                    "error": "All questions must have mappings configured before continuing",
                    "questions_missing_mappings": missing,
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )

    stage_records = PipelineStage.query.filter_by(pipeline_run_id=run_id).all()
    stage_status = {stage.stage_name: stage.status for stage in stage_records}

    # Determine which downstream stages still need to run
    downstream_order = [
        PipelineStageEnum.PDF_CREATION.value,
        PipelineStageEnum.RESULTS_GENERATION.value,
    ]
    remaining_stages = [
        stage_name
        for stage_name in downstream_order
        if stage_status.get(stage_name) != "completed"
    ]

    if not remaining_stages:
        return (
            jsonify({
                "error": "No remaining stages to continue",
                "current_status": run.status,
                "stages": stage_status,
            }),
            HTTPStatus.BAD_REQUEST,
        )

    smart_service = SmartSubstitutionService()
    smart_service.sync_structured_mappings(run_id)
    current_app.logger.info(
        "Structured mappings synchronized before downstream pipeline trigger",
        extra={"run_id": run_id},
    )

    orchestrator = PipelineOrchestrator()

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
        "questions_with_mappings": len(questions),
        "total_questions": len(questions),
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
			sequence_index=q.sequence_index,
			source_identifier=q.source_identifier,
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

        # Preserve previously generated artifacts (span plans, debug captures, etc.)
        source_artifacts_dir = source_run_dir / "artifacts"
        if source_artifacts_dir.exists():
            dest_artifacts_dir = run_directory(new_id) / "artifacts"
            shutil.rmtree(dest_artifacts_dir, ignore_errors=True)
            shutil.copytree(source_artifacts_dir, dest_artifacts_dir, dirs_exist_ok=True)

        structured_copy = copy.deepcopy(structured or {})

        def _rewrite_run_references(value: object) -> object:
            if isinstance(value, dict):
                return {key: _rewrite_run_references(inner) for key, inner in value.items()}
            if isinstance(value, list):
                return [_rewrite_run_references(item) for item in value]
            if isinstance(value, str) and source_run_id in value:
                return value.replace(source_run_id, new_id)
            return value

        document_info = structured_copy.setdefault("document", {})
        if dest_pdf_path:
            document_info["source_path"] = str(dest_pdf_path)
            document_info.setdefault("filename", dest_pdf_path.name)
        elif source_pdf_path:
            document_info.setdefault("source_path", str(source_pdf_path))
            document_info.setdefault("filename", source_pdf_path.name)

        metadata = structured_copy.setdefault("pipeline_metadata", {})
        metadata["run_id"] = new_id
        metadata["rerun_from"] = source_run_id
        metadata["current_stage"] = "smart_substitution"
        metadata["stages_completed"] = ["smart_reading", "content_discovery"]
        metadata["last_updated"] = isoformat(utc_now())
        metadata.pop("completed_at", None)
        metadata.pop("completion_summary", None)
        metadata.pop("final_summary", None)
        metadata.pop("result_digest", None)

        # Reset downstream stage artefacts so the re-run generates fresh outputs
        original_manip_results = structured_copy.get("manipulation_results") or {}
        preserved_artifacts = copy.deepcopy(original_manip_results.get("artifacts") or {})
        preserved_debug = copy.deepcopy(original_manip_results.get("debug") or {})

        for entry in preserved_debug.values():
            if not isinstance(entry, dict):
                continue
            entry.pop("span_plan_summary", None)
            entry.pop("span_plan", None)
            entry.pop("scaled_spans", None)
            overlay_layers = entry.get("overlay_layers")
            if isinstance(overlay_layers, dict):
                for overlay_entry in overlay_layers.values():
                    if isinstance(overlay_entry, dict):
                        overlay_entry.pop("span_plan_summary", None)
                        overlay_entry.pop("span_plan", None)
                        overlay_entry.pop("scaled_spans", None)

        structured_copy["manipulation_results"] = {"enhanced_pdfs": {}}
        if preserved_artifacts:
            structured_copy["manipulation_results"]["artifacts"] = preserved_artifacts
        if preserved_debug:
            structured_copy["manipulation_results"]["debug"] = preserved_debug
        structured_copy.pop("performance_metrics", None)
        structured_copy.pop("global_mappings", None)

        structured_copy = _rewrite_run_references(structured_copy)

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
					sequence_index=q.sequence_index,
					source_identifier=q.source_identifier,
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

