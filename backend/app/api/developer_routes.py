from __future__ import annotations

import json
import uuid
from http import HTTPStatus

from flask import Blueprint, jsonify

from ..extensions import sock
from ..models import PerformanceMetric, PipelineLog, PipelineRun
from ..services.developer.live_logging_service import live_logging_service
from ..services.developer.ai_analysis_debugger import AIAnalysisDebugger
from ..services.data_management.structured_data_manager import StructuredDataManager
from ..services.ai_clients.ai_client_orchestrator import AIClientOrchestrator


def _client_status(client: object) -> dict[str, bool]:
	"""Return a normalized availability payload for optional AI clients."""
	if not client:
		return {"configured": False, "available": False}
	try:
		configured = bool(client.is_configured())  # type: ignore[attr-defined]
	except Exception:  # noqa: BLE001
		configured = False
	return {"configured": configured, "available": configured}


bp = Blueprint("developer", __name__, url_prefix="/developer")


def init_app(api_bp: Blueprint) -> None:
    api_bp.register_blueprint(bp)


@bp.get("/<run_id>/logs")
def list_logs(run_id: str):
    logs = (
        PipelineLog.query.filter_by(pipeline_run_id=run_id)
        .order_by(PipelineLog.timestamp.desc())
        .limit(200)
        .all()
    )

    return jsonify(
        {
            "run_id": run_id,
            "logs": [
                {
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "level": log.level,
                    "stage": log.stage,
                    "component": log.component,
                    "message": log.message,
                    "metadata": log.context,
                }
                for log in logs
            ],
        }
    )


@bp.get("/<run_id>/metrics")
def list_metrics(run_id: str):
    metrics = (
        PerformanceMetric.query.filter_by(pipeline_run_id=run_id)
        .order_by(PerformanceMetric.created_at.desc())
        .all()
    )

    return jsonify(
        {
            "run_id": run_id,
            "metrics": [
                {
                    "stage": metric.stage,
                    "metric_name": metric.metric_name,
                    "metric_value": metric.metric_value,
                    "metric_unit": metric.metric_unit,
                    "metadata": metric.details,
                    "recorded_at": metric.created_at.isoformat() if metric.created_at else None,
                }
                for metric in metrics
            ],
        }
    )


@bp.get("/<run_id>/ai-debug")
def debug_ai_extraction(run_id: str):
    """Get AI extraction debugging information."""
    run = PipelineRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Pipeline run not found"}), HTTPStatus.NOT_FOUND

    structured_manager = StructuredDataManager()
    try:
        structured_data = structured_manager.load(run_id)
    except Exception:
        return jsonify({"error": "No structured data found"}), HTTPStatus.NOT_FOUND

    # Extract AI analysis data
    ai_extraction = structured_data.get("ai_extraction", {})

    if not ai_extraction:
        return jsonify({"error": "No AI extraction data found"}), HTTPStatus.NOT_FOUND

    debugger = AIAnalysisDebugger()

    # Create simplified debug report with available data
    debug_report = {
        "run_id": run_id,
        "ai_extraction_summary": ai_extraction,
        "ai_questions_found": structured_data.get("ai_questions", []),
        "pymupdf_baseline": {
            "document": structured_data.get("document", {}),
            "content_elements_count": len(structured_data.get("content_elements", [])),
            "assets": structured_data.get("assets", {})
        }
    }

    return jsonify(debug_report)


@bp.get("/ai-clients/test")
def test_ai_clients():
    """Test all AI client configurations."""
    orchestrator = AIClientOrchestrator()

    test_results = {
        "openai_vision": _client_status(orchestrator.openai_client),
        "mistral_ocr": _client_status(orchestrator.mistral_client),
        "gpt5_fusion": _client_status(getattr(orchestrator, "gpt5_fusion_client", None)),
    }

    return jsonify(test_results)


@bp.get("/<run_id>/structured-data")
def get_structured_data(run_id: str):
    """Get raw structured data for debugging."""
    structured_manager = StructuredDataManager()

    try:
        data = structured_manager.load(run_id)
        return jsonify({
            "run_id": run_id,
            "data": data,
            "size": len(str(data)),
            "keys": list(data.keys()) if isinstance(data, dict) else []
        })
    except Exception as e:
        return jsonify({"error": str(e)}), HTTPStatus.NOT_FOUND


@bp.get("/system/health")
def system_health():
    """Get overall system health check."""
    orchestrator = AIClientOrchestrator()

    health = {
        "database": True,  # If we got here, database is working
        "ai_clients": {
            "openai_vision": _client_status(orchestrator.openai_client),
            "mistral_ocr": _client_status(orchestrator.mistral_client),
            "gpt5_fusion": _client_status(getattr(orchestrator, "gpt5_fusion_client", None)),
        },
        "storage": True,  # Basic assumption
        "websockets": True  # Basic assumption
    }

    # Overall health status
    health["status"] = "healthy" if all([
        health["database"],
        health["storage"],
        health["websockets"],
        any(status.get("configured") for status in health["ai_clients"].values()),
    ]) else "degraded"

    return jsonify(health)


# IMPORTANT: expose websocket under /api prefix to match frontend expectations
@sock.route("/api/developer/logs/<run_id>/stream")
def log_stream(ws, run_id: str):  # pragma: no cover - websocket plumbing
    if not PipelineRun.query.get(run_id):
        ws.close(HTTPStatus.NOT_FOUND)
        return

    for event in live_logging_service.stream_logs(run_id):
        ws.send(json.dumps(event))
