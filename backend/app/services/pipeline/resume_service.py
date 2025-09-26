from __future__ import annotations

from ...extensions import db
from ...models import PipelineRun, PipelineStage
from ...utils.exceptions import ResourceNotFound


class PipelineResumeService:
    def mark_for_resume(self, run_id: str, stage_name: str) -> None:
        run = PipelineRun.query.get(run_id)
        if not run:
            raise ResourceNotFound("Pipeline run not found")

        stage = PipelineStage.query.filter_by(pipeline_run_id=run_id, stage_name=stage_name).first()
        if not stage:
            stage = PipelineStage(
                pipeline_run_id=run_id,
                stage_name=stage_name,
                status="pending",
            )
        else:
            stage.status = "pending"
            stage.error_details = None
            stage.started_at = None
            stage.completed_at = None

        run.status = "pending"
        run.current_stage = stage_name
        db.session.add(run)
        db.session.add(stage)
        db.session.commit()
