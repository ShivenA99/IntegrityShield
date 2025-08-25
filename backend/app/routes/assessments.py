from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import List
import logging

from flask import Blueprint, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename

from .. import db
from ..models import Assessment, StoredFile, Question, LLMResponse
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

# Debug artefacts directory (repo root ./output)
DEBUG_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
DEBUG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Set via env: ENABLE_LLM=0 to disable all LLM calls during testing
ENABLE_LLM = os.getenv("ENABLE_LLM", "1") not in {"0", "false", "False"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@assessments_bp.route("/upload", methods=["POST"])
def upload_assessment():
    """Handle upload of original Q-paper and answers paper, create attacked versions, call LLM, save report."""

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------
    attack_type_str = request.form.get("attack_type", AttackType.NONE.value)
    logger.info("[upload_assessment] Received upload request with attack_type=%s", attack_type_str)
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

    # ------------------------------------------------------------------
    # Create directory for this assessment
    # ------------------------------------------------------------------
    assessment_uuid = uuid.uuid4()
    assessment_dir = UPLOAD_DIR / "assessments" / str(assessment_uuid)
    assessment_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("[upload_assessment] Created assessment directory %s", assessment_dir)

    # Save uploaded PDFs
    orig_path = assessment_dir / secure_filename(orig_file.filename)
    orig_file.save(orig_path)
    ans_path: Path | None = None
    if ans_file and ans_file.filename:
        ans_path = assessment_dir / secure_filename(ans_file.filename)
        ans_file.save(ans_path)

    # Record StoredFile entries
    orig_sf = StoredFile(path=str(orig_path), mime_type="application/pdf")
    db.session.add(orig_sf)
    ans_sf: StoredFile | None = None
    if ans_path:
        ans_sf = StoredFile(path=str(ans_path), mime_type="application/pdf")
        db.session.add(ans_sf)
    db.session.flush()  # obtain IDs

    # ------------------------------------------------------------------
    # Parse original PDF – get title and question list
    # ------------------------------------------------------------------
    title_text, questions = parse_pdf_questions(orig_path)
    logger.info("[upload_assessment] Parsing PDF and injecting attacks (%s)", attack_type.value)
    inject_attacks_into_questions(questions, attack_type)

    # ------------------------------------------------------------------
    # Generate wrong answers & rationales – leverage answer key when present
    # ------------------------------------------------------------------
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
                # Generate input/output entities via LLM for CODE_GLYPH
                try:
                    from ..services.wrong_answer_service import generate_wrong_answer_entities
                    entities = generate_wrong_answer_entities(q["stem_text"], q["options"], correct_label)
                    q["code_glyph_entities"] = entities  # {input_entity, output_entity, wrong_label, rationale, ...}
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
            # Prevention mode: No wrong-answer generation; keep placeholders empty
            wrong_label, wrong_reason = "", ""
        else:
            wrong_label, wrong_reason = generate_wrong_answer(
                stem_text=q["stem_text"],
                options=q["options"],
                correct_answer=correct_label,
            )

        q["wrong_label"] = wrong_label
        q["wrong_reason"] = wrong_reason

        logger.debug(f"[upload_assessment] Q{q['q_number']}: Generated wrong answer = {wrong_label}, reason = {wrong_reason}")

        if correct_label:
            q["gold_answer"] = correct_label
            q["gold_reason"] = correct_reason
            logger.debug(f"[upload_assessment] Q{q['q_number']}: Found correct answer = {correct_label}")

    # Create attacked PDF
    attacked_pdf_path = assessment_dir / "attacked.pdf"
    if attack_type == AttackType.CODE_GLYPH:
        try:
            from ..services.attacks import get_attack_handler
            handler = get_attack_handler("CODE_GLYPH")
            if handler:
                generated_path, _ = handler.build_artifacts(questions, assessment_dir, title_text)
                # Copy or point attacked.pdf to the generated file location for consistency
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

    # ------------------------------------------------------------------
    # Evaluate attacked PDF with OpenAI
    # ------------------------------------------------------------------
    evaluation_results = None
    logger.info(f"[upload_assessment] ENABLE_LLM={ENABLE_LLM}, attack_type={attack_type}, attack_type!=NONE={attack_type != AttackType.NONE}")
    if ENABLE_LLM and attack_type != AttackType.NONE:
        try:
            # Prepare reference and malicious answers
            reference_answers = {}
            malicious_answers = {}
            
            for q in questions:
                q_num = q["q_number"]
                # Reference answer (correct answer)
                if "gold_answer" in q and q["gold_answer"]:
                    reference_answers[q_num] = q["gold_answer"]
                    logger.debug(f"[upload_assessment] Q{q_num}: Reference answer = {q['gold_answer']}")
                
                # Malicious answer (wrong answer that was generated)
                if "wrong_label" in q and q["wrong_label"]:
                    malicious_answers[q_num] = q["wrong_label"]
                    logger.debug(f"[upload_assessment] Q{q_num}: Malicious answer = {q['wrong_label']}")
            
            logger.debug(f"[upload_assessment] Found {len(reference_answers)} reference answers and {len(malicious_answers)} malicious answers")
            
            if questions:
                # If no reference answers are available, we can still evaluate
                if not reference_answers:
                    logger.info("[upload_assessment] No reference answers available, evaluating attack effectiveness only")
                    reference_answers = {q["q_number"]: "UNKNOWN" for q in questions}
                
                if attack_type == AttackType.CODE_GLYPH:
                    try:
                        from ..services.attacks import get_attack_handler
                        handler = get_attack_handler("CODE_GLYPH")
                        if handler:
                            logger.info("[upload_assessment] Starting CODE_GLYPH evaluation")
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
                            logger.warning("[upload_assessment] CODE_GLYPH handler missing; falling back to OpenAI evaluation")
                            logger.info("[upload_assessment] Starting OpenAI PDF evaluation")
                            evaluation_results = evaluate_pdf_with_openai(
                                attacked_pdf_path=attacked_pdf_path,
                                questions=questions,
                                reference_answers=reference_answers
                            )
                    except Exception as exc:
                        logger.error("[upload_assessment] CODE_GLYPH evaluation failed; fallback to OpenAI evaluation: %s", exc)
                        logger.info("[upload_assessment] Starting OpenAI PDF evaluation")
                        evaluation_results = evaluate_pdf_with_openai(
                            attacked_pdf_path=attacked_pdf_path,
                            questions=questions,
                            reference_answers=reference_answers
                        )
                elif attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION:
                    logger.info("[upload_assessment] Starting PREVENTION evaluation (answers-only accuracy)")
                    from ..services.openai_eval_service import evaluate_prevention_pdf_with_openai
                    evaluation_results = evaluate_prevention_pdf_with_openai(
                        attacked_pdf_path=attacked_pdf_path,
                        questions=questions,
                    )
                else:
                    logger.info("[upload_assessment] Starting OpenAI PDF evaluation")
                    evaluation_results = evaluate_pdf_with_openai(
                        attacked_pdf_path=attacked_pdf_path,
                        questions=questions,
                        reference_answers=reference_answers
                    )
                logger.info(f"[upload_assessment] OpenAI evaluation completed")
            else:
                logger.warning("[upload_assessment] Skipping OpenAI evaluation - no questions found")
                
        except Exception as exc:
            logger.error(f"[upload_assessment] OpenAI evaluation failed: {exc}")
            evaluation_results = None

    # ------------------------------------------------------------------
    # Always generate reference report (with evaluation results if available)
    # ------------------------------------------------------------------
    report_path = assessment_dir / "reference_report.pdf"
    build_reference_report(questions, report_path, evaluation_results)

    attacked_sf = StoredFile(path=str(attacked_pdf_path), mime_type="application/pdf")
    report_sf = StoredFile(path=str(report_path), mime_type="application/pdf")

    db.session.add_all([attacked_sf, report_sf])
    db.session.flush()

    # ------------------------------------------------------------------
    # Persist Assessment + Question + LLMResponse rows
    # ------------------------------------------------------------------
    assessment = Assessment(
        id=assessment_uuid,
        attack_type=attack_type.value,
        original_pdf_id=orig_sf.id,
        answers_pdf_id=ans_sf.id if ans_sf else None,
        attacked_pdf_id=attacked_sf.id,
        report_pdf_id=report_sf.id,
    )
    db.session.add(assessment)
    db.session.flush()

    question_rows = []
    llm_rows = []
    
    # Check if questions already exist for this assessment to prevent duplicates
    existing_questions = Question.query.filter_by(assessment_id=assessment.id).all()
    if existing_questions:
        logger.warning(f"[upload_assessment] Questions already exist for assessment {assessment_uuid}, cleaning up existing questions")
        # Delete existing questions to allow re-insertion
        for existing_q in existing_questions:
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
        question_rows.append(q_row)
        db.session.add(q_row)
        db.session.flush()

        if "llm_response" in q:
            llm_rows.append(
                LLMResponse(
                    question_id=q_row.id,
                    model_name="perplexity",
                    llm_answer=q["llm_response"].get("answer_text", ""),
                    raw_json=q["llm_response"].get("raw"),
                )
            )

    if llm_rows:
        db.session.add_all(llm_rows)

    try:
        db.session.commit()
        logger.info("[upload_assessment] Assessment %s processed successfully", assessment_uuid)
    except Exception as e:
        db.session.rollback()
        logger.error(f"[upload_assessment] Failed to commit assessment {assessment_uuid}: {e}")
        
        # Check if it's a unique constraint violation
        if "UniqueViolation" in str(e) and "uq_questions_assessment_qnum" in str(e):
            logger.error(f"[upload_assessment] Duplicate question numbers detected for assessment {assessment_uuid}")
            # Clean up the assessment directory and files
            try:
                import shutil
                if assessment_dir.exists():
                    shutil.rmtree(assessment_dir)
                logger.info(f"[upload_assessment] Cleaned up assessment directory {assessment_dir}")
            except Exception as cleanup_error:
                logger.error(f"[upload_assessment] Failed to cleanup assessment directory: {cleanup_error}")
            
            return jsonify({"error": "Duplicate question numbers detected. Please try uploading again."}), 400
        
        raise

    # ------------------------------------------------------------------
    # Copy artefacts to ./output for quick manual inspection
    # ------------------------------------------------------------------
    try:
        shutil.copy(attacked_pdf_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_attacked.pdf")
        shutil.copy(report_path, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_reference_report.pdf")
        # Also export the LaTeX source so developers can quickly inspect
        # rendering issues in the generated PDF.
        try:
            tex_src = attacked_pdf_path.with_suffix(".tex")
            if tex_src.exists():
                shutil.copy(tex_src, DEBUG_OUTPUT_DIR / f"{assessment_uuid}_attacked.tex")
        except Exception:
            pass
    except Exception as exc:
        logger.debug("[upload_assessment] Could not copy PDFs to output dir: %s", exc)

    return jsonify({"assessment_id": str(assessment.id)}), 201


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