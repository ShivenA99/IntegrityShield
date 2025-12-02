from __future__ import annotations

import asyncio
from statistics import mean
from typing import Any, Dict

from ...extensions import db
from ...models import PipelineRun
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now


class ResultsGenerationService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.structured_manager = StructuredDataManager()

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._generate_results, run_id)

    def _generate_results(self, run_id: str) -> Dict[str, Any]:
        structured = self.structured_manager.load(run_id)
        metadata = structured.setdefault("pipeline_metadata", {})
        questions = structured.get("questions", [])

        raw_scores = [q.get("manipulation", {}).get("effectiveness_score") for q in questions]
        numeric_scores = [float(score) for score in raw_scores if isinstance(score, (int, float))]
        avg_effectiveness = mean(numeric_scores) if numeric_scores else 0.0

        summary = {
            "questions": len(questions),
            "average_effectiveness": round(avg_effectiveness, 3),
            "generated_at": isoformat(utc_now()),
        }

        structured.setdefault("manipulation_results", {})["summary"] = summary
        stages_completed = set(metadata.get("stages_completed", []))
        stages_completed.add("results_generation")
        metadata.update(
            {
                "current_stage": "results_generation",
                "stages_completed": list(stages_completed),
                "last_updated": summary["generated_at"],
            }
        )

        self.structured_manager.save(run_id, structured)

        run = PipelineRun.query.get(run_id)
        if run:
            run.processing_stats = {"average_effectiveness": avg_effectiveness}
            db.session.add(run)
            db.session.commit()

        # Auto-report generation now handled by orchestrator post-stage hooks
        return summary
