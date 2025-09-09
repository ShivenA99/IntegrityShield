from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import List
import logging
import datetime as dt

from flask import Blueprint, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename

from .. import db
from ..models import Assessment, StoredFile, Question, LLMResponse, Job
from ..services import attack_service
from ..services.attack_service import AttackType
from ..services.pdf_utils import (
    parse_pdf_questions,
    inject_attacks_into_questions,
    build_attacked_pdf,
    build_reference_report,
    parse_pdf_answers,
    build_code_glyph_report,
)
from ..services.wrong_answer_service import generate_wrong_answer
from ..services.openai_eval_service import (
    evaluate_pdf_with_openai,
    evaluate_code_glyph_pdf_with_openai,
    write_code_glyph_eval_artifacts,
)

logger = logging.getLogger(__name__)

assessments_bp = Blueprint("assessments", __name__)

_default_data_dir = Path.cwd() / "data"
UPLOAD_DIR = Path(os.getenv("DATA_DIR", str(_default_data_dir))).resolve()

ALLOWED_EXTENSIONS = {"pdf"}

def allowed_file(filename: str) -> bool:
    try:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    except Exception:
        return False

def get_or_create_stored_file(file_path: Path, mime_type: str) -> StoredFile:
    existing: StoredFile | None = StoredFile.query.filter_by(path=str(file_path)).first()
    if existing:
        return existing
    sf = StoredFile(path=str(file_path), mime_type=mime_type)
    db.session.add(sf)
    db.session.flush()
    return sf

# Debug artefacts directory (repo root ./output)
DEBUG_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
DEBUG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Set via env: ENABLE_LLM=0 to disable all LLM calls during testing
ENABLE_LLM = os.getenv("ENABLE_LLM", "0") not in {"0", "false", "False"}
STOP_AFTER_OCR = os.getenv("STOP_AFTER_OCR", "0") in {"1", "true", "True"}
STOP_AFTER_STRUCTURING = os.getenv("STOP_AFTER_STRUCTURING", "0") in {"1", "true", "True"}
STOP_AFTER_WA = os.getenv("STOP_AFTER_WA", "0") in {"1", "true", "True"}
STOP_AFTER_RENDER = os.getenv("STOP_AFTER_RENDER", "1") in {"1", "true", "True"}

from sqlalchemy import func


@assessments_bp.route("/upload", methods=["POST"])
def upload_assessment():
    """Handle upload of original Q-paper and answers paper, create attacked versions, call LLM, save report."""
    job = None
    try:
        # Input validation
        attack_type_str = request.form.get("attack_type", AttackType.NONE.value)
        client_id_str = request.form.get("client_id")
        logger.info("[upload_assessment] Received upload request with attack_type=%s client_id=%s", attack_type_str, client_id_str)
        try:
            attack_type = AttackType(attack_type_str)
            logger.info("[upload_assessment] Parsed attack_type=%s", attack_type)
        except ValueError:
            logger.error("[upload_assessment] Invalid attack_type: %s", attack_type_str)
            return jsonify({"error": "Invalid attack_type"}), 400

        if "original_pdf" not in request.files:
            return jsonify({"error": "original_pdf file is required."}), 400

        orig_file = request.files["original_pdf"]
        ans_file = request.files.get("answers_pdf")

        if not (orig_file and allowed_file(orig_file.filename)):
            return jsonify({"error": "original_pdf must be a PDF."}), 400
        if ans_file and not allowed_file(ans_file.filename):
            return jsonify({"error": "answers_pdf must be a PDF if provided."}), 400

        # Always create a new Assessment directory and ID (do not reuse)
        assessment_uuid = uuid.uuid4()
        assessment_dir = UPLOAD_DIR / "assessments" / str(assessment_uuid)
        assessment_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("[upload_assessment] Created assessment directory %s", assessment_dir)

        # Setup per-run logging to a file inside assessment_dir/code_glyph/run.log
        try:
            from ..services.logging_utils import activate_run_context, create_run_file_handler, attach_run_file_handler
            run_log_path = assessment_dir / "code_glyph" / "run.log"
            activate_run_context(str(assessment_uuid))
            _run_file_handler = create_run_file_handler(run_log_path)
            attach_run_file_handler(_run_file_handler)
            logger.info("[upload_assessment] Run-scoped logging initialized at %s", run_log_path)
        except Exception as _e_setup_log:
            logger.warning("[upload_assessment] Failed to initialize run-scoped logging: %s", _e_setup_log)

        # Save uploaded PDFs
        orig_path = assessment_dir / secure_filename(orig_file.filename)
        orig_file.save(orig_path)
        ans_path: Path | None = None
        if ans_file and ans_file.filename:
            ans_path = assessment_dir / secure_filename(ans_file.filename)
            ans_file.save(ans_path)

        # Create StoredFile entries (new rows)
        orig_sf = StoredFile(path=str(orig_path), mime_type="application/pdf")
        db.session.add(orig_sf)
        ans_sf: StoredFile | None = None
        if ans_path:
            ans_sf = StoredFile(path=str(ans_path), mime_type="application/pdf")
            db.session.add(ans_sf)
        db.session.flush()

        # Create Assessment
        assessment = Assessment(
            id=assessment_uuid,
            attack_type=attack_type.value,
            original_pdf_id=orig_sf.id,
            answers_pdf_id=ans_sf.id if ans_sf else None,
        )
        db.session.add(assessment)
        db.session.flush()

        # Create running job (progress will be updated below)
        job = Job(
            assessment_id=assessment.id,
            action="upload",
            params={"attack_type": attack_type.value},
            status="running",
            progress=10,
            message="Saving files",
            queued_at=dt.datetime.utcnow(),
            started_at=dt.datetime.utcnow(),
        )
        db.session.add(job)
        db.session.flush()

        # Parse original PDF – get title and question list
        job.progress = 20
        job.message = "Parsing & injecting"
        db.session.flush()

        # If STOP_AFTER_OCR is enabled, run only layout + asset extraction and return early for UI testing
        if STOP_AFTER_OCR:
            try:
                from ..services.layout_extractor import extract_layout_and_assets
                assets_dir = assessment_dir / "assets"
                logger.info("[upload_assessment] STOP_AFTER_OCR=1; extracting layout and assets only")
                ocr_doc = extract_layout_and_assets(orig_path, assets_dir, dpi=int(os.getenv("STRUCTURE_OCR_DPI", "300")))
                # Persist structured.json
                import json
                structured_path = assessment_dir / "structured.json"
                with open(structured_path, "w", encoding="utf-8") as f:
                    json.dump(ocr_doc, f, ensure_ascii=False, indent=2)

                # Mirror to debug output
                try:
                    shutil.copy(structured_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_structured.json")
                except Exception:
                    pass

                # Finalize job and return early
                job.status = "succeeded"
                job.progress = 100
                job.message = "OCR extraction complete"
                job.finished_at = dt.datetime.utcnow()
                db.session.commit()

                return jsonify({
                    "assessment_id": str(assessment.id),
                    "structured_json": str(structured_path),
                    "assets_dir": str(assets_dir),
                    "note": "STOP_AFTER_OCR enabled; skipped attack/build/eval."
                }), 201
            except Exception as exc_ocr:
                logger.exception("[upload_assessment] STOP_AFTER_OCR extraction failed: %s", exc_ocr)
                return jsonify({"error": "OCR extraction failed"}), 500

        # If STOP_AFTER_STRUCTURING is enabled, run layout + LLM structuring and return early
        if STOP_AFTER_STRUCTURING:
            try:
                from ..services.layout_extractor import extract_layout_and_assets
                from ..services.ocr_service import extract_structured_document_with_ocr
                from ..services.ocr_postprocess import postprocess_document
                assets_dir = assessment_dir / "assets"
                logger.info("[upload_assessment] STOP_AFTER_STRUCTURING=1; extracting layout + structuring only")
                layout_doc = extract_layout_and_assets(orig_path, assets_dir, dpi=int(os.getenv("STRUCTURE_OCR_DPI", "300")))
                structured_doc = extract_structured_document_with_ocr(orig_path, layout_doc)
                # Post-process: dedup assets and prefer images for non-question text
                structured_doc = postprocess_document(orig_path, structured_doc, assets_dir, questions=structured_doc.get("document", {}).get("questions", []), dpi=int(os.getenv("STRUCTURE_OCR_DPI", "300")))
                # Persist structured.json
                import json
                structured_path = assessment_dir / "structured.json"
                with open(structured_path, "w", encoding="utf-8") as f:
                    json.dump(structured_doc, f, ensure_ascii=False, indent=2)

                # Mirror to debug output
                try:
                    shutil.copy(structured_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_structured.json")
                except Exception:
                    pass

                # Finalize job and return early
                job.status = "succeeded"
                job.progress = 100
                job.message = "OCR structuring complete"
                job.finished_at = dt.datetime.utcnow()
                db.session.commit()

                return jsonify({
                    "assessment_id": str(assessment.id),
                    "structured_json": str(structured_path),
                    "assets_dir": str(assets_dir),
                    "note": "STOP_AFTER_STRUCTURING enabled; skipped attack/build/eval."
                }), 201
            except Exception as exc_ocr2:
                logger.exception("[upload_assessment] STOP_AFTER_STRUCTURING failed: %s", exc_ocr2)
                return jsonify({"error": "OCR structuring failed"}), 500

        # STOP_AFTER_WA: generate wrong answers/entities by attack & q_type, persist, and return early
        if STOP_AFTER_WA:
            try:
                from ..services.layout_extractor import extract_layout_and_assets
                from ..services.ocr_service import extract_structured_document_with_ocr
                from ..services.ocr_postprocess import postprocess_document
                from ..services.wrong_answer_service import generate_wrong_answer_for_question

                assets_dir = assessment_dir / "assets"
                logger.info("[upload_assessment] STOP_AFTER_WA=1; layout + structuring + wrong-answer generation only")
                layout_doc = extract_layout_and_assets(orig_path, assets_dir, dpi=int(os.getenv("STRUCTURE_OCR_DPI", "300")))
                structured_doc = extract_structured_document_with_ocr(orig_path, layout_doc)
                structured_doc = postprocess_document(orig_path, structured_doc, assets_dir, questions=structured_doc.get("document", {}).get("questions", []), dpi=int(os.getenv("STRUCTURE_OCR_DPI", "300")))

                # Per-question WA/entities
                doc = structured_doc.get("document", {})
                qs = doc.get("questions", [])
                for q in qs:
                    try:
                        wa = generate_wrong_answer_for_question(q, attack_type, structured_doc)
                        if wa:
                            q.update(wa)
                    except Exception as e:
                        logger.warning("[upload_assessment] WA generation failed for Q%s: %s", q.get("q_number"), e)

                # Persist structured.json with WA fields
                import json
                structured_path = assessment_dir / "structured.json"
                with open(structured_path, "w", encoding="utf-8") as f:
                    json.dump(structured_doc, f, ensure_ascii=False, indent=2)

                try:
                    shutil.copy(structured_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_structured.json")
                except Exception:
                    pass

                job.status = "succeeded"
                job.progress = 100
                job.message = "Wrong-answer generation complete"
                job.finished_at = dt.datetime.utcnow()
                db.session.commit()

                return jsonify({
                    "assessment_id": str(assessment.id),
                    "structured_json": str(structured_path),
                    "assets_dir": str(assets_dir),
                    "note": "STOP_AFTER_WA enabled; skipped build/eval."
                }), 201
            except Exception as exc_wa:
                logger.exception("[upload_assessment] STOP_AFTER_WA failed: %s", exc_wa)
                return jsonify({"error": "Wrong-answer generation failed"}), 500

        # STOP_AFTER_RENDER: run layout -> structuring -> postprocess -> (WA if detection/code_glyph) -> render attacked PDF via MuPDF
        if STOP_AFTER_RENDER:
            try:
                from ..services.layout_extractor import extract_layout_and_assets
                from ..services.ocr_service import extract_structured_document_with_ocr
                from ..services.ocr_postprocess import postprocess_document
                from ..services.wrong_answer_service import generate_wrong_answer_for_question
                from ..services.pdf_renderer_mupdf import build_attacked_pdf_mupdf
                from ..services.reference_report_builder import build_reference_report_pdf

                assets_dir = assessment_dir / "assets"
                logger.info("[upload_assessment] STOP_AFTER_RENDER=1; rendering attacked PDF via MuPDF")
                layout_doc = extract_layout_and_assets(orig_path, assets_dir, dpi=int(os.getenv("STRUCTURE_OCR_DPI", "300")))
                structured_doc = extract_structured_document_with_ocr(orig_path, layout_doc)
                structured_doc = postprocess_document(orig_path, structured_doc, assets_dir, questions=structured_doc.get("document", {}).get("questions", []), dpi=int(os.getenv("STRUCTURE_OCR_DPI", "300")))

                # Ensure source path is recorded for background import
                try:
                    if isinstance(structured_doc.get("document"), dict):
                        structured_doc["document"]["source_path"] = str(orig_path)
                except Exception:
                    pass

                # For detection or code glyph, generate WA/entities before rendering
                if attack_type in {AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP, AttackType.CODE_GLYPH}:
                    doc = structured_doc.get("document", {})
                    qs = doc.get("questions", [])
                    for q in qs:
                        try:
                            wa = generate_wrong_answer_for_question(q, attack_type, structured_doc)
                            if wa:
                                q.update(wa)
                        except Exception as e:
                            logger.warning("[upload_assessment] WA generation failed for Q%s: %s", q.get("q_number"), e)

                attacked_pdf_path = assessment_dir / "attacked.pdf"
                if attack_type == AttackType.CODE_GLYPH:
                    from ..services.pdf_renderer_mupdf import build_attacked_pdf_code_glyph
                    prebuilt_dir = Path(os.getenv("CODE_GLYPH_PREBUILT_DIR", ""))
                    if not prebuilt_dir or not prebuilt_dir.exists():
                        raise RuntimeError("CODE_GLYPH_PREBUILT_DIR not configured or not found.")
                    build_attacked_pdf_code_glyph(structured_doc, attacked_pdf_path, prebuilt_dir)
                else:
                    build_attacked_pdf_mupdf(orig_path, structured_doc, attacked_pdf_path, attack_type)

                # Persist structured.json too
                import json
                structured_path = assessment_dir / "structured.json"
                with open(structured_path, "w", encoding="utf-8") as f:
                    json.dump(structured_doc, f, ensure_ascii=False, indent=2)

                # Build and persist reference report in fast path
                report_path = assessment_dir / "reference_report.pdf"
                try:
                    # Infer attack type for report builder
                    from ..services.attack_service import AttackType as _AT
                    doc = structured_doc.get("document", {})
                    qs = doc.get("questions", [])
                    # Title for report
                    title_text = doc.get("title") or ""
                    
                    logger.info(f"Building reference report with {len(qs)} questions, title='{title_text}'")
                    
                    # Build report PDF (no evaluations in fast path)
                    build_reference_report_pdf(
                        questions=qs,
                        attacked_pdf_path=attacked_pdf_path,
                        structured_json_path=structured_path,
                        assets_dir=assessment_dir / "assets",
                        output_path=report_path,
                        attack_type=attack_type,
                        reference_answers=None,
                        evaluations=None
                    )
                    logger.info(f"Reference report successfully created at {report_path}")
                except Exception as e:
                    # If report build fails, continue with attacked only
                    logger.error(f"Reference report building failed: {e}")
                    logger.info("Falling back to simple report generation")
                    try:
                        from ..services.pdf_utils import build_reference_report
                        build_reference_report(qs, report_path, None)
                        logger.info(f"Fallback report created at {report_path}")
                    except Exception as e2:
                        logger.error(f"Fallback report also failed: {e2}")
                        report_path = None

                # Save debug copies
                try:
                    shutil.copy(attacked_pdf_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_attacked.pdf")
                    shutil.copy(structured_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_structured.json")
                    if report_path and Path(report_path).exists():
                        shutil.copy(report_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_report.pdf")
                except Exception:
                    pass

                # Create StoredFile entries and attach to assessment for downloads
                attacked_sf = get_or_create_stored_file(attacked_pdf_path, "application/pdf")
                report_sf = get_or_create_stored_file(report_path, "application/pdf") if report_path and Path(report_path).exists() else None
                assessment.attacked_pdf = attacked_sf
                if report_sf:
                    assessment.report_pdf = report_sf
                db.session.flush()

                job.status = "succeeded"
                job.progress = 100
                job.message = "Rendered attacked PDF (fast path)"
                job.finished_at = dt.datetime.utcnow()
                db.session.commit()

                return jsonify({
                    "assessment_id": str(assessment.id),
                    "structured_json": str(structured_path),
                    "assets_dir": str(assets_dir),
                    "attacked_pdf": str(attacked_pdf_path),
                    "report_pdf": (str(report_path) if report_path and Path(report_path).exists() else None),
                    "downloads": {
                        "original": f"/api/assessments/{assessment.id}/original",
                        "attacked": f"/api/assessments/{assessment.id}/attacked",
                        "report": f"/api/assessments/{assessment.id}/report",
                    },
                    "note": "STOP_AFTER_RENDER enabled; skipped evaluation."
                }), 201
            except Exception as exc_render:
                logger.exception("[upload_assessment] STOP_AFTER_RENDER failed: %s", exc_render)
                return jsonify({"error": "Render failed"}), 500

        title_text, questions = parse_pdf_questions(orig_path)
        logger.info("[upload_assessment] Parsing PDF and injecting attacks (%s)", attack_type.value)
        inject_attacks_into_questions(questions, attack_type)

        # Generate wrong answers & rationales – leverage answer key when present
        answer_key: dict[int, tuple[str, str]] = {}
        if ans_path:
            try:
                answer_key = parse_pdf_answers(ans_path)
                logger.debug("[upload_assessment] Parsed %d answers from key PDF", len(answer_key))
            except Exception as exc:
                logger.warning("[upload_assessment] Failed to parse answers_pdf: %s", exc)

        for q in questions:
            correct_label, correct_reason = answer_key.get(q["q_number"], (None, "")) if answer_key else (None, "")
            if attack_type == AttackType.CODE_GLYPH:
                try:
                    from ..services.attacks import get_attack_handler
                    handler = get_attack_handler("CODE_GLYPH")
                    try:
                        from ..services.wrong_answer_service import generate_wrong_answer_entities
                        entities = generate_wrong_answer_entities(q["stem_text"], q["options"], correct_label)
                        q["code_glyph_entities"] = entities
                        logger.info("[upload_assessment] CODE_GLYPH entities for Q%s: %s", q["q_number"], entities)
                    except Exception as exc_ent:
                        logger.error("[upload_assessment] CODE_GLYPH entity generation failed: %s", exc_ent)
                    if handler:
                        wrong_label, wrong_reason = handler.generate_wrong_answer(
                            stem_text=q["stem_text"],
                            options=q["options"],
                            correct_answer=correct_label,
                        )
                    else:
                        wrong_label, wrong_reason = generate_wrong_answer(
                            stem_text=q["stem_text"],
                            options=q["options"],
                            correct_answer=correct_label,
                        )
                except Exception as exc:
                    logger.error("[upload_assessment] CODE_GLYPH wrong-answer generation failed; fallback to default: %s", exc)
                    wrong_label, wrong_reason = generate_wrong_answer(
                        stem_text=q["stem_text"],
                        options=q["options"],
                        correct_answer=correct_label,
                    )
            elif attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION:
                wrong_label, wrong_reason = "", ""
            else:
                wrong_label, wrong_reason = generate_wrong_answer(
                    stem_text=q["stem_text"],
                    options=q["options"],
                    correct_answer=correct_label,
                )

            q["wrong_label"] = wrong_label
            q["wrong_reason"] = wrong_reason
            if correct_label:
                q["gold_answer"] = correct_label
                q["gold_reason"] = correct_reason

        job.progress = 50
        job.message = "Building attacked PDF"
        db.session.flush()

        # Create attacked PDF
        attacked_pdf_path = assessment_dir / "attacked.pdf"
        if attack_type == AttackType.CODE_GLYPH:
            try:
                from ..services.attacks import get_attack_handler
                handler = get_attack_handler("CODE_GLYPH")
                if handler:
                    generated_path, _ = handler.build_artifacts(questions, assessment_dir, title_text)
                    if generated_path != attacked_pdf_path:
                        try:
                            import shutil
                            shutil.copyfile(generated_path, attacked_pdf_path)
                        except Exception:
                            attacked_pdf_path = generated_path
                else:
                    build_attacked_pdf(questions, attacked_pdf_path, title=title_text)
            except Exception as exc:
                logger.error("[upload_assessment] CODE_GLYPH build failed, falling back: %s", exc)
                build_attacked_pdf(questions, attacked_pdf_path, title=title_text)
        else:
            build_attacked_pdf(questions, attacked_pdf_path, title=title_text)

        job.progress = 70
        job.message = "Evaluating"
        db.session.flush()

        # Evaluate attacked PDF with OpenAI
        evaluation_results = None
        logger.info(f"[upload_assessment] ENABLE_LLM={ENABLE_LLM}, attack_type={attack_type}, attack_type!=NONE={attack_type != AttackType.NONE}")
        if ENABLE_LLM and attack_type != AttackType.NONE:
            try:
                reference_answers = {}
                malicious_answers = {}
                for q in questions:
                    q_num = q["q_number"]
                    if "gold_answer" in q and q["gold_answer"]:
                        reference_answers[q_num] = q["gold_answer"]
                    if "wrong_label" in q and q["wrong_label"]:
                        malicious_answers[q_num] = q["wrong_label"]
                if questions:
                    if not reference_answers:
                        reference_answers = {q["q_number"]: "UNKNOWN" for q in questions}
                    if attack_type == AttackType.CODE_GLYPH:
                        try:
                            from ..services.attacks import get_attack_handler
                            handler = get_attack_handler("CODE_GLYPH")
                            if handler:
                                from ..services.openai_eval_service import evaluate_code_glyph_pdf_with_openai, write_code_glyph_eval_artifacts
                                evaluation_results = evaluate_code_glyph_pdf_with_openai(
                                    attacked_pdf_path=attacked_pdf_path,
                                    questions=questions,
                                )
                                try:
                                    write_code_glyph_eval_artifacts(assessment_dir, questions, evaluation_results)
                                except Exception:
                                    pass
                            else:
                                evaluation_results = evaluate_pdf_with_openai(
                                    attacked_pdf_path=attacked_pdf_path,
                                    questions=questions,
                                    reference_answers=reference_answers
                                )
                        except Exception as exc:
                            logger.error("[upload_assessment] CODE_GLYPH evaluation failed; fallback to OpenAI evaluation: %s", exc)
                            evaluation_results = evaluate_pdf_with_openai(
                                attacked_pdf_path=attacked_pdf_path,
                                questions=questions,
                                reference_answers=reference_answers
                            )
                    elif attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION:
                        from ..services.openai_eval_service import evaluate_prevention_pdf_with_openai
                        evaluation_results = evaluate_prevention_pdf_with_openai(
                            attacked_pdf_path=attacked_pdf_path,
                            questions=questions,
                        )
                    else:
                        evaluation_results = evaluate_pdf_with_openai(
                            attacked_pdf_path=attacked_pdf_path,
                            questions=questions,
                            reference_answers=reference_answers
                        )
            except Exception as exc:
                logger.error(f"[upload_assessment] OpenAI evaluation failed: {exc}")
                evaluation_results = None

        job.progress = 85
        job.message = "Building report"
        db.session.flush()

        # Always generate reference report
        report_path = assessment_dir / "reference_report.pdf"
        
        # Try to use questions from structured.json if available (has context_ids for visuals)
        # but merge with database evaluation data
        structured_path = assessment_dir / "structured.json"
        questions_for_report = questions  # Default fallback
        logger.info(f"DEBUG: Looking for structured.json at {structured_path}")
        logger.info(f"DEBUG: structured.json exists: {structured_path.exists()}")
        if structured_path.exists():
            try:
                import json
                with open(structured_path, 'r', encoding='utf-8') as f:
                    structured_doc = json.load(f)
                structured_questions = structured_doc.get("document", {}).get("questions", [])
                if structured_questions:
                    logger.info(f"Using {len(structured_questions)} questions from structured.json for report")
                    
                    # Get database questions for evaluation data
                    db_questions = Question.query.filter_by(assessment_id=assessment.id).all()
                    db_question_map = {q.q_number: q for q in db_questions}
                    
                    logger.info(f"DEBUG: Found {len(db_questions)} database questions")
                    for db_q in db_questions:
                        logger.info(f"DEBUG: DB Q{db_q.q_number}: gold='{db_q.gold_answer}', wrong='{db_q.wrong_answer}'")
                    
                    # Merge structured questions with database evaluation data
                    for structured_q in structured_questions:
                        q_num = structured_q.get("q_number")
                        logger.info(f"DEBUG: Structured Q{q_num} looking for match in DB")
                        if q_num in db_question_map:
                            db_q = db_question_map[q_num]
                            # Add database evaluation data to structured question
                            structured_q["gold_answer"] = db_q.gold_answer
                            structured_q["gold_reason"] = db_q.gold_reason
                            structured_q["wrong_answer"] = db_q.wrong_answer
                            structured_q["wrong_reason"] = db_q.wrong_reason
                            logger.info(f"DEBUG: Merged Q{q_num}: gold='{db_q.gold_answer}', wrong='{db_q.wrong_answer}'")
                            # Also add code_glyph_entities if it exists in original questions
                            for orig_q in questions:
                                if orig_q.get("q_number") == q_num and "code_glyph_entities" in orig_q:
                                    structured_q["code_glyph_entities"] = orig_q["code_glyph_entities"]
                                    break
                        else:
                            logger.warning(f"DEBUG: No DB match for structured Q{q_num}")
                            logger.info(f"DEBUG: Available DB question numbers: {list(db_question_map.keys())}")
                    
                    questions_for_report = structured_questions
            except Exception as e:
                logger.warning(f"Failed to load questions from structured.json: {e}")
        else:
            logger.info("DEBUG: structured.json doesn't exist, using original questions")
            # Add evaluation data directly to original questions
            db_questions = Question.query.filter_by(assessment_id=assessment.id).all()
            db_question_map = {q.q_number: q for q in db_questions}
            
            logger.info(f"DEBUG: Found {len(db_questions)} database questions")
            for db_q in db_questions:
                logger.info(f"DEBUG: DB Q{db_q.q_number}: gold='{db_q.gold_answer}', wrong='{db_q.wrong_answer}'")
            
            # Merge database data into original questions
            for orig_q in questions_for_report:
                q_num = orig_q.get("q_number")
                if q_num in db_question_map:
                    db_q = db_question_map[q_num]
                    orig_q["gold_answer"] = db_q.gold_answer
                    orig_q["gold_reason"] = db_q.gold_reason  
                    orig_q["wrong_answer"] = db_q.wrong_answer
                    orig_q["wrong_reason"] = db_q.wrong_reason
                    logger.info(f"DEBUG: Merged Q{q_num}: gold='{db_q.gold_answer}', wrong='{db_q.wrong_answer}'")
        
        # Generate reference report using the new professional builder
        try:
            build_reference_report_pdf(
                questions=questions_for_report,
                attacked_pdf_path=attacked_pdf_path,
                structured_json_path=structured_path,
                assets_dir=assessment_dir / "assets",
                output_path=report_path,
                attack_type=attack_type,
                reference_answers=None,
                evaluations=evaluation_results
            )
            logger.info(f"Professional reference report created at {report_path}")
        except Exception as e:
            logger.error(f"Professional report failed: {e}, falling back to simple report")
            # Fallback to old report if new one fails
            build_reference_report(questions_for_report, report_path, evaluation_results)

        attacked_sf = StoredFile(path=str(attacked_pdf_path), mime_type="application/pdf")
        report_sf = StoredFile(path=str(report_path), mime_type="application/pdf")
        db.session.add_all([attacked_sf, report_sf])
        db.session.flush()

        # Update assessment outputs
        assessment.attacked_pdf_id = attacked_sf.id
        assessment.report_pdf_id = report_sf.id
        db.session.flush()

        # Replace Questions (fresh per run)
        for existing_q in Question.query.filter_by(assessment_id=assessment.id).all():
            db.session.delete(existing_q)
        db.session.flush()
        for q in questions:
            q_row = Question(
                assessment_id=assessment.id,
                q_number=q["q_number"],
                stem_text=q["stem_text"],
                options_json=q["options"],
                gold_answer=q.get("gold_answer", ""),
                gold_reason=q.get("gold_reason", ""),
                wrong_answer=q.get("wrong_label", ""),
                wrong_reason=q.get("wrong_reason", ""),
                attacked_stem=q["attacked_stem"],
            )
            db.session.add(q_row)
        db.session.commit()

        # Finalize job
        job.status = "succeeded"
        job.progress = 100
        job.message = "Completed"
        job.finished_at = dt.datetime.utcnow()
        db.session.commit()

        # Copy artefacts
        try:
            shutil.copy(attacked_pdf_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_attacked.pdf")
            shutil.copy(report_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_reference_report.pdf")
            try:
                tex_src = attacked_pdf_path.with_suffix(".tex")
                if tex_src.exists():
                    shutil.copy(tex_src, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_attacked.tex")
            except Exception:
                pass
        except Exception as exc:
            logger.debug("[upload_assessment] Could not copy PDFs to output dir: %s", exc)

        return jsonify({"assessment_id": str(assessment.id)}), 201
    except Exception as e:
        logger.exception("[upload_assessment] Failed: %s", e)
        if job:
            try:
                job.status = "failed"
                job.message = "Failed"
                job.finished_at = dt.datetime.utcnow()
                db.session.commit()
            except Exception:
                pass
        return jsonify({"error": "Upload failed"}), 500
    finally:
        try:
            from ..services.logging_utils import detach_run_file_handler
            if '_run_file_handler' in locals():
                detach_run_file_handler(_run_file_handler)
        except Exception:
            pass


@assessments_bp.route("/<uuid:assessment_id>/attacked", methods=["GET"])
def download_attacked(assessment_id):
    assessment: Assessment | None = Assessment.query.get(assessment_id)
    if not assessment or not assessment.attacked_pdf:
        return jsonify({"error": "Assessment not found"}), 404
    
    response = send_file(assessment.attacked_pdf.path, as_attachment=True)
    # Force download by setting cache control headers
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@assessments_bp.route("/<uuid:assessment_id>/report", methods=["GET"])
def download_report(assessment_id):
    assessment: Assessment | None = Assessment.query.get(assessment_id)
    if not assessment or not assessment.report_pdf:
        return jsonify({"error": "Assessment not found"}), 404
    
    response = send_file(assessment.report_pdf.path, as_attachment=True)
    # Force download by setting cache control headers
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@assessments_bp.route("/<uuid:assessment_id>/original", methods=["GET"])
def download_original(assessment_id):
    assessment: Assessment | None = Assessment.query.get(assessment_id)
    if not assessment or not assessment.original_pdf:
        return jsonify({"error": "Assessment not found"}), 404

    response = send_file(assessment.original_pdf.path, as_attachment=True)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@assessments_bp.route("/", methods=["GET"])
def list_assessments():
    """Paginated list of assessments with filtering/sorting.
    """
    q = request.args.get("q", type=str)
    attack_type = request.args.get("attack_type", type=str)
    start = request.args.get("start", type=str)
    end = request.args.get("end", type=str)
    sort = request.args.get("sort", default="created_at", type=str)
    order = request.args.get("order", default="desc", type=str)
    page = request.args.get("page", default=1, type=int)
    page_size = max(1, min(100, request.args.get("page_size", default=20, type=int)))

    query = Assessment.query.filter(Assessment.is_deleted == False)  # noqa: E712

    # Filters
    if attack_type:
        query = query.filter(Assessment.attack_type == attack_type)
    # Date range
    try:
        if start:
            start_dt = dt.datetime.fromisoformat(start)
            query = query.filter(Assessment.created_at >= start_dt)
        if end:
            end_dt = dt.datetime.fromisoformat(end)
            query = query.filter(Assessment.created_at <= end_dt)
    except Exception:
        return jsonify({"error": "Invalid start/end datetime format. Use ISO 8601."}), 400

    # Filename search on original
    if q:
        query = query.join(Assessment.original_pdf)
        query = query.filter(func.lower(func.split_part(StoredFile.path, '/', -1)).like(f"%{q.lower()}%"))

    # Sorting
    sort_map = {
        "created_at": Assessment.created_at,
        "attack_type": Assessment.attack_type,
        "status": Assessment.status,
        "original_filename": func.split_part(StoredFile.path, '/', -1),
    }

    if sort == "original_filename":
        query = query.join(Assessment.original_pdf)

    sort_col = sort_map.get(sort, Assessment.created_at)

    if order.lower() == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # Pagination
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    def to_item(a: Assessment):
        import os
        return {
            "id": str(a.id),
            "created_at": a.created_at.isoformat(),
            "attack_type": a.attack_type,
            "status": a.status,
            "original_filename": os.path.basename(a.original_pdf.path) if a.original_pdf else None,
            "answers_filename": os.path.basename(a.answers_pdf.path) if a.answers_pdf else None,
            "attacked_filename": os.path.basename(a.attacked_pdf.path) if a.attacked_pdf else None,
            "report_filename": os.path.basename(a.report_pdf.path) if a.report_pdf else None,
            "downloads": {
                "original": f"/api/assessments/{a.id}/original",
                "attacked": f"/api/assessments/{a.id}/attacked",
                "report": f"/api/assessments/{a.id}/report",
            },
        }

    return jsonify({
        "items": [to_item(a) for a in items],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    })


@assessments_bp.route("/bulk-delete", methods=["POST"])
def bulk_delete():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "ids must be a non-empty array"}), 400
    updated = 0
    for id_str in ids:
        try:
            aid = uuid.UUID(id_str)
        except Exception:
            continue
        a: Assessment | None = Assessment.query.get(aid)
        if a and not a.is_deleted:
            a.is_deleted = True
            a.deleted_at = dt.datetime.utcnow()
            updated += 1
    db.session.commit()
    return jsonify({"deleted": updated}), 200


@assessments_bp.route("/<uuid:assessment_id>/rerun", methods=["POST"])
def rerun_assessment(assessment_id):
    a: Assessment | None = Assessment.query.get(assessment_id)
    if not a or a.is_deleted:
        return jsonify({"error": "Assessment not found"}), 404
    body = request.get_json(silent=True) or {}
    params = {
        "attack_type": body.get("attack_type", a.attack_type),
        "flags": body.get("flags", {}),
    }
    # Create job in queued state
    job = Job(
        assessment_id=a.id,
        action="rerun",
        params=params,
        status="queued",
        progress=0,
        message="Queued",
        order_index=0,
    )
    db.session.add(job)
    db.session.commit()
    return jsonify({"job_id": str(job.id)}), 202






@assessments_bp.route("/files/tree", methods=["GET"])
def files_tree():
    path = request.args.get("path", "/")
    root = UPLOAD_DIR / "assessments"
    target = root if path == "/" else (root / path.strip("/"))
    if not target.exists() or not target.is_dir():
        return jsonify({"error": "Not found"}), 404
    items = []
    for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        items.append({
            "name": p.name,
            "type": "folder" if p.is_dir() else "file",
            "modified_at": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            "size": p.stat().st_size,
            "path": str((target / p.name).relative_to(root)).replace("\\", "/"),
        })
    return jsonify({"path": path, "items": items})


@assessments_bp.route("/<uuid:assessment_id>/evaluate", methods=["POST"])
def evaluate_assessment(assessment_id):
    """Manually trigger evaluation of an existing assessment with OpenAI."""
    assessment: Assessment | None = Assessment.query.get(assessment_id)
    if not assessment:
        return jsonify({"error": "Assessment not found"}), 404
    
    if not ENABLE_LLM:
        return jsonify({"error": "LLM evaluation is disabled"}), 400
    
    try:
        # Get the attacked PDF path
        attacked_pdf_path = Path(assessment.attacked_pdf.path)
        if not attacked_pdf_path.exists():
            return jsonify({"error": "Attacked PDF not found"}), 404
        
        # Get questions and answers from the database
        questions = Question.query.filter_by(assessment_id=assessment.id).all()
        
        # Prepare reference and malicious answers
        reference_answers = {}
        malicious_answers = {}
        
        for q in questions:
            q_num = q.q_number
            # Reference answer (correct answer)
            if q.gold_answer:
                reference_answers[q_num] = q.gold_answer
            
            # For malicious answers, we need to get the wrong answer that was generated
            if q.wrong_answer:
                malicious_answers[q_num] = q.wrong_answer
        
        if not reference_answers or not malicious_answers:
            return jsonify({"error": "Missing reference or malicious answers"}), 400
        
        # Perform evaluation
        evaluation_results = evaluate_pdf_with_openai(
            attacked_pdf_path=attacked_pdf_path,
            reference_answers=reference_answers,
            malicious_answers=malicious_answers
        )
        
        return jsonify({
            "assessment_id": str(assessment.id),
            "evaluation": evaluation_results
        }), 200
        
    except Exception as exc:
        logger.error(f"[evaluate_assessment] Evaluation failed: {exc}")
        return jsonify({"error": f"Evaluation failed: {str(exc)}"}), 500 