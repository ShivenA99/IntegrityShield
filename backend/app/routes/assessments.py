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
)
from ..services.wrong_answer_service import generate_wrong_answer

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
    except ValueError:
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

    # Create attacked PDF
    attacked_pdf_path = assessment_dir / "attacked.pdf"
    build_attacked_pdf(questions, attacked_pdf_path, title=title_text)

    # ------------------------------------------------------------------
    # Always generate reference report (no external LLM evaluation phase)
    # ------------------------------------------------------------------
    report_path = assessment_dir / "reference_report.pdf"
    build_reference_report(questions, report_path)

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
    for q in questions:
        q_row = Question(
            assessment_id=assessment.id,
            q_number=q["q_number"],
            stem_text=q["stem_text"],
            options_json=q["options"],
            gold_answer=q.get("gold_answer", ""),
            gold_reason=q.get("gold_reason", ""),
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

    db.session.commit()
    logger.info("[upload_assessment] Assessment %s processed successfully", assessment_uuid)

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
    return send_file(assessment.attacked_pdf.path, as_attachment=True)


@assessments_bp.route("/<uuid:assessment_id>/report", methods=["GET"])
def download_report(assessment_id):
    assessment: Assessment | None = Assessment.query.get(assessment_id)
    if not assessment or not assessment.report_pdf:
        return jsonify({"error": "Assessment not found"}), 404
    return send_file(assessment.report_pdf.path, as_attachment=True) 