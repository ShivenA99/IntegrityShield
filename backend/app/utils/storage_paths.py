from __future__ import annotations

from pathlib import Path
from typing import Tuple

from flask import current_app


METHOD_FOLDER_OVERRIDES = {
    "pymupdf_overlay": "redaction-rewrite-overlay",
    "content_stream_overlay": "stream_rewrite-overlay",
}


def pipeline_root() -> Path:
    base = current_app.config["PIPELINE_STORAGE_ROOT"]
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_directory(run_id: str) -> Path:
    path = pipeline_root() / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def assets_directory(run_id: str) -> Path:
    path = run_directory(run_id) / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def answer_sheets_directory(run_id: str) -> Path:
    path = run_directory(run_id) / "answer_sheets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def classroom_dataset_directory(run_id: str, classroom_key: str) -> Path:
    safe_key = classroom_key or "default"
    path = answer_sheets_directory(run_id) / safe_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def classroom_evaluations_directory(run_id: str) -> Path:
    path = run_directory(run_id) / "classroom_evaluations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def classroom_evaluation_artifact(run_id: str, classroom_key: str, filename: str) -> Path:
    path = classroom_evaluations_directory(run_id) / classroom_key / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def detection_report_directory(run_id: str) -> Path:
    path = run_directory(run_id) / "detection_report"
    path.mkdir(parents=True, exist_ok=True)
    return path


def structured_data_path(run_id: str) -> Path:
    return run_directory(run_id) / "structured.json"


def pdf_input_path(run_id: str, filename: str) -> Path:
    return run_directory(run_id) / filename


def enhanced_pdf_path(run_id: str, method_name: str) -> Path:
    if method_name in METHOD_FOLDER_OVERRIDES:
        return _artifact_folder(run_id, method_name) / "final.pdf"
    return run_directory(run_id) / f"enhanced_{method_name}.pdf"


def report_paths(run_id: str) -> Tuple[Path, Path, Path]:
    base = run_directory(run_id)
    return (
        base / "analysis_report.pdf",
        base / "results_dashboard.pdf",
        base / "developer_debug.json",
    )


def method_stage_artifact_path(run_id: str, method_key: str, stage_name: str) -> Path:
    base = artifacts_root(run_id) / method_key
    base.mkdir(parents=True, exist_ok=True)
    filename = stage_name if "." in stage_name else f"{stage_name}.pdf"
    path = base / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
def artifacts_root(run_id: str) -> Path:
    path = run_directory(run_id) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _artifact_folder(run_id: str, method_name: str) -> Path:
    folder = METHOD_FOLDER_OVERRIDES.get(method_name, method_name)
    path = artifacts_root(run_id) / folder
    path.mkdir(parents=True, exist_ok=True)
    return path
