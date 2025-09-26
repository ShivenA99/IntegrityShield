from __future__ import annotations

from pathlib import Path
from typing import Tuple

from flask import current_app


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


def structured_data_path(run_id: str) -> Path:
    return run_directory(run_id) / "structured.json"


def pdf_input_path(run_id: str, filename: str) -> Path:
    return run_directory(run_id) / filename


def enhanced_pdf_path(run_id: str, method_name: str) -> Path:
    return run_directory(run_id) / f"enhanced_{method_name}.pdf"


def report_paths(run_id: str) -> Tuple[Path, Path, Path]:
    base = run_directory(run_id)
    return (
        base / "analysis_report.pdf",
        base / "results_dashboard.pdf",
        base / "developer_debug.json",
    )
