from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Blueprint, jsonify, send_file

from ..models import PipelineRun
from ..utils.storage_paths import run_directory


bp = Blueprint("files", __name__, url_prefix="/files")


def init_app(api_bp: Blueprint) -> None:
    api_bp.register_blueprint(bp)


@bp.get("/<run_id>/<path:filename>")
def download_run_file(run_id: str, filename: str):
    """Serve a file from the run's storage directory with path traversal protection."""

    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    base = run_directory(run_id).resolve()
    target = (base / filename).resolve()

    # Prevent path traversal
    try:
        target.relative_to(base)
    except ValueError:
        return jsonify({"error": "Invalid path"}), HTTPStatus.BAD_REQUEST

    if not target.exists() or not target.is_file():
        return jsonify({"error": "File not found"}), HTTPStatus.NOT_FOUND

    # Let the browser preview PDFs inline; user can still download via UI
    return send_file(str(target), as_attachment=False)
