from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable

from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.intelligence.effectiveness_analyzer import summarize_effectiveness
from ...services.intelligence.multi_model_tester import MultiModelTester
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now


class EffectivenessTestingService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.structured_manager = StructuredDataManager()
        self.tester = MultiModelTester()

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        models = config.get("ai_models")
        return await asyncio.to_thread(self._evaluate_questions, run_id, models)

    def _evaluate_questions(self, run_id: str, models: Iterable[str] | None) -> Dict[str, Any]:
        questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
        combined_results = []

        for question in questions:
            results = self.tester.test_question(run_id, question.id, models=models)
            combined_results.extend(results.values())

        summary = summarize_effectiveness(combined_results)

        structured = self.structured_manager.load(run_id)
        summary.setdefault("models_tested", summary.get("models_tested", 0))
        structured.setdefault("manipulation_results", {})["effectiveness_summary"] = summary

        metadata = structured.setdefault("pipeline_metadata", {})
        stages_completed = set(metadata.get("stages_completed", []))
        stages_completed.add("effectiveness_testing")
        metadata.update(
            {
                "current_stage": "effectiveness_testing",
                "stages_completed": list(stages_completed),
                "last_updated": isoformat(utc_now()),
            }
        )
        self.structured_manager.save(run_id, structured)

        return summary
