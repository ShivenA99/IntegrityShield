from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from flask import Blueprint, current_app, jsonify, send_file

import csv
import json

try:  # Lazy import; thumbnail route will check again.
    import fitz  # type: ignore
except Exception:  # noqa: BLE001
    fitz = None


demo_bp = Blueprint("demo", __name__, url_prefix="/demo")


def init_app(api_bp: Blueprint) -> None:
    api_bp.register_blueprint(demo_bp)


def _assets_root() -> Path:
    config_path = current_app.config.get("DEMO_ASSETS_PATH")
    if config_path:
        return Path(config_path).resolve()
    # default: repository_root/demo_assets
    project_root = Path(current_app.root_path).resolve().parent.parent
    return (project_root / "demo_assets").resolve()


def _derive_display_name(run_dir: Path) -> Tuple[str, Optional[str], Optional[str]]:
    input_path = _resolve_pdf_path(run_dir.name, "input")
    attacked_path = _resolve_pdf_path(run_dir.name, "attacked")
    if input_path:
        display = input_path.name
        input_label = input_path.name
        attacked_label = attacked_path.name if attacked_path else None
        return display, input_label, attacked_label
    return run_dir.name.replace("_", " ").title(), None, None


def _collect_runs() -> List[Dict[str, object]]:
    root = _assets_root()
    runs: List[Dict[str, object]] = []
    if not root.exists():
        return runs
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        run_id = child.name
        if run_id.lower() == "paper_c":
            continue
        display, input_filename, attacked_filename = _derive_display_name(child)
        input_path = _resolve_pdf_path(run_id, "input")
        attacked_path = _resolve_pdf_path(run_id, "attacked")
        files = {
            "input_pdf": bool(input_path),
            "attacked_pdf": bool(attacked_path),
            "vulnerability_report": (child / "vulnerability_report.csv").exists()
            or (child / "vulnerability_report.json").exists(),
            "reference_report": (child / "reference_report.csv").exists()
            or (child / "reference_report.json").exists(),
        }
        runs.append(
            {
                "id": run_id,
                "display_name": display,
                "input_filename": input_filename,
                "attacked_filename": attacked_filename,
                "files": files,
            }
        )
    return runs


def _load_csv_rows(csv_path: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    with csv_path.open("r", encoding="utf-8-sig") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            rows.append(dict(row))
    return rows


def _load_json_rows(json_path: Path) -> List[Dict[str, object]]:
    with json_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        questions = data.get("questions")
        if isinstance(questions, list):
            return questions
    return []


def _normalize_overview_entry(entry: Dict[str, object]) -> Dict[str, object]:
    ai = entry.get("AI") or entry.get("ai") or entry.get("model")
    correct = entry.get("Correct") or entry.get("correct")
    incorrect = entry.get("Incorrect") or entry.get("incorrect")
    total = entry.get("Total") or entry.get("total")
    accuracy = entry.get("Accuracy") or entry.get("accuracy")

    def _to_float(value: object) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _to_string(value: object) -> str:
        return str(value).strip() if value is not None else ""

    correct_f = _to_float(correct) or 0.0
    incorrect_f = _to_float(incorrect) or 0.0
    total_f = _to_float(total) or (correct_f + incorrect_f)
    accuracy_f = _to_float(accuracy)
    if accuracy_f is None and total_f:
        accuracy_f = correct_f / total_f

    return {
        "AI": _to_string(ai) or "Unknown",
        "Correct": correct_f,
        "Incorrect": incorrect_f,
        "Total": total_f,
        "Accuracy": accuracy_f if accuracy_f is not None else 0.0,
    }


def _load_report_overview(run_id: str, base_name: str) -> List[Dict[str, object]]:
    run_dir = _assets_root() / run_id
    json_path = run_dir / f"{base_name}.json"
    if json_path.exists():
        try:
            with json_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and isinstance(data.get("overview"), list):
                return [
                    _normalize_overview_entry(item)
                    for item in data["overview"]
                    if isinstance(item, dict)
                ]
            if isinstance(data, list):
                return [
                    _normalize_overview_entry(item)
                    for item in data
                    if isinstance(item, dict)
                ]
        except Exception as exc:  # noqa: BLE001
            current_app.logger.warning(
                "Failed to parse demo JSON",
                extra={"run_id": run_id, "file": json_path.name, "error": str(exc)},
            )

    # Some datasets embed the overview inside the questions file
    questions_json_path = run_dir / f"{base_name.replace('_report', '_questions')}.json"
    if questions_json_path.exists():
        try:
            with questions_json_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and isinstance(data.get("overview"), list):
                return [
                    _normalize_overview_entry(item)
                    for item in data["overview"]
                    if isinstance(item, dict)
                ]
        except Exception as exc:  # noqa: BLE001
            current_app.logger.warning(
                "Failed to parse embedded overview",
                extra={"run_id": run_id, "file": questions_json_path.name, "error": str(exc)},
            )

    csv_path = run_dir / f"{base_name}.csv"
    if csv_path.exists():
        try:
            rows = _load_csv_rows(csv_path)
            return [_normalize_overview_entry(row) for row in rows]
        except Exception as exc:  # noqa: BLE001
            current_app.logger.warning(
                "Failed to parse demo CSV",
                extra={"run_id": run_id, "file": csv_path.name, "error": str(exc)},
            )

    return [
        {
            "AI": "Placeholder",
            "Correct": 0.0,
            "Incorrect": 0.0,
            "Total": 0.0,
            "Accuracy": 0.0,
        }
    ]


def _load_question_details(run_id: str, base_name: str) -> List[Dict[str, object]]:
    run_dir = _assets_root() / run_id
    json_path = run_dir / f"{base_name}.json"
    if not json_path.exists():
        return []
    try:
        with json_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict):
            questions = data.get("questions")
            if isinstance(questions, list):
                return questions
        return _load_json_rows(json_path)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning(
            "Failed to parse question report",
            extra={"run_id": run_id, "file": json_path.name, "error": str(exc)},
        )
        return []


def _compute_overview_from_questions(questions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    model_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {
        "ai": "",
        "correct": 0.0,
        "incorrect": 0.0,
        "total": 0.0,
    })

    def determine_result(entry: Dict[str, object]) -> Optional[str]:
        result = entry.get("result")
        if isinstance(result, str) and result:
            lowered = result.lower()
            if lowered in {"correct", "incorrect"}:
                return lowered

        symbol = entry.get("result_symbol") or entry.get("resultSymbol")
        if isinstance(symbol, str):
            symbol = symbol.strip()
            if symbol in {"✓", "✔"}:
                return "correct"
            if symbol in {"✗", "✘"}:
                return "incorrect"

        status = entry.get("status")
        if isinstance(status, str):
            lowered = status.lower()
            if lowered in {"correct", "incorrect"}:
                return lowered
        return None

    for question in questions:
        if not isinstance(question, dict):
            continue
        answers = []
        if isinstance(question.get("llm_answers"), list):
            answers = question["llm_answers"]  # type: ignore[assignment]
        elif isinstance(question.get("llmAnswers"), list):
            answers = question["llmAnswers"]  # type: ignore[assignment]
        elif isinstance(question.get("aiEvaluations"), list):
            answers = question["aiEvaluations"]  # type: ignore[assignment]

        for ans in answers:
            if not isinstance(ans, dict):
                continue
            model = ans.get("model")
            if not isinstance(model, str) or not model.strip():
                continue
            model_name = model.strip()
            stats = model_stats[model_name]
            stats["ai"] = model_name
            stats["total"] += 1
            result = determine_result(ans)
            if result == "correct":
                stats["correct"] += 1
            elif result == "incorrect":
                stats["incorrect"] += 1

    overview = []
    for model_name in sorted(model_stats.keys()):
        stats = model_stats[model_name]
        total = stats["total"] or 1
        accuracy = stats["correct"] / total
        overview.append({
            "ai": model_name,
            "correct": stats["correct"],
            "incorrect": stats["incorrect"],
            "total": stats["total"],
            "accuracy": accuracy,
        })

    return overview


@demo_bp.get("/runs")
def list_runs() -> object:
    return jsonify({"runs": _collect_runs()})


@demo_bp.get("/runs/<run_id>/vulnerability")
def get_vulnerability_report(run_id: str) -> object:
    questions = _load_question_details(run_id, "vulnerability_questions")
    overview = _load_report_overview(run_id, "vulnerability_report")
    if not overview or overview[0].get("AI") == "Placeholder":
        overview = _compute_overview_from_questions(questions)
    return jsonify({"overview": overview, "questions": questions})


@demo_bp.get("/runs/<run_id>/reference")
def get_reference_report(run_id: str) -> object:
    questions = _load_question_details(run_id, "reference_questions")
    overview = _load_report_overview(run_id, "reference_report")
    if not overview or overview[0].get("AI") == "Placeholder":
        overview = _compute_overview_from_questions(questions)
    return jsonify({"overview": overview, "questions": questions})


def _resolve_pdf_path(run_id: str, kind: str) -> Path | None:
    run_dir = _assets_root() / run_id
    if not run_dir.exists():
        return None

    canonical = run_dir / (
        "input.pdf" if kind == "input" else "attacked.pdf"
    )
    if canonical.exists():
        return canonical

    pdf_candidates = sorted(run_dir.glob("*.pdf"))
    if not pdf_candidates:
        return None

    def is_attacked(path: Path) -> bool:
        stem = path.stem.lower()
        return any(token in stem for token in ("anticheat", "attack", "attacked"))

    if kind == "attacked":
        for candidate in pdf_candidates:
            if is_attacked(candidate):
                return candidate
        # fall back to the last candidate if nothing matches naming convention
        return pdf_candidates[-1]

    # input: prefer anything that does not look like an attacked asset
    for candidate in pdf_candidates:
        if not is_attacked(candidate):
            return candidate
    return pdf_candidates[0]


def _thumbnail_path(run_dir: Path, kind: str) -> Path:
    return run_dir / f"{kind}_thumb.png"


def _ensure_thumbnail(run_id: str, kind: str) -> Optional[Path]:
    if fitz is None:
        return None
    pdf_path = _resolve_pdf_path(run_id, kind)
    if not pdf_path or not pdf_path.exists():
        return None

    run_dir = pdf_path.parent
    thumb_path = _thumbnail_path(run_dir, kind)
    if thumb_path.exists() and thumb_path.stat().st_mtime >= pdf_path.stat().st_mtime:
        return thumb_path

    try:
        with fitz.open(pdf_path) as doc:  # type: ignore[call-arg]
            if doc.page_count == 0:
                return None
            page = doc.load_page(0)
            matrix = fitz.Matrix(0.6, 0.6)  # type: ignore[attr-defined]
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pix.save(thumb_path)
        return thumb_path
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning(
            "Failed to generate demo thumbnail",
            extra={"run_id": run_id, "kind": kind, "error": str(exc)},
        )
        return None


@demo_bp.get("/runs/<run_id>/pdf/<kind>")
def get_demo_pdf(run_id: str, kind: str):
    target_kind = kind.lower()
    if target_kind not in {"input", "attacked"}:
        return jsonify({"error": "unknown_pdf_kind"}), 404

    pdf_path = _resolve_pdf_path(run_id, target_kind)
    if not pdf_path or not pdf_path.exists():
        return jsonify({"error": "file_not_found"}), 404

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        download_name=pdf_path.name,
        as_attachment=False,
    )


@demo_bp.get("/runs/<run_id>/pdf/<kind>/thumbnail")
def get_demo_pdf_thumbnail(run_id: str, kind: str):
    target_kind = kind.lower()
    if target_kind not in {"input", "attacked"}:
        return jsonify({"error": "unknown_pdf_kind"}), 404

    run_dir = _assets_root() / run_id
    thumb_path = _thumbnail_path(run_dir, target_kind)
    if not thumb_path.exists():
        thumb_path = _ensure_thumbnail(run_id, target_kind)
    if not thumb_path or not thumb_path.exists():
        return jsonify({"error": "thumbnail_not_available"}), 404

    return send_file(thumb_path, mimetype="image/png")
