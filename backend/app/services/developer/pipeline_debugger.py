from __future__ import annotations

from typing import Any, Dict

from ...models import PipelineRun


def serialize_run(run: PipelineRun) -> Dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "current_stage": run.current_stage,
        "pipeline_config": run.pipeline_config,
        "processing_stats": run.processing_stats,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }
