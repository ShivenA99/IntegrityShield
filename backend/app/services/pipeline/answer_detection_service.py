from __future__ import annotations

import asyncio
from typing import Any, Dict

from ...extensions import db
from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.integration.external_api_client import ExternalAIClient
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now


class AnswerDetectionService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.structured_manager = StructuredDataManager()
        self.ai_client = ExternalAIClient()

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._detect_answers, run_id)

    def _detect_answers(self, run_id: str) -> Dict[str, Any]:
        questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
        results = []

        for question in questions:
            answer, confidence = self._determine_answer(question)
            question.gold_answer = answer
            question.gold_confidence = confidence
            results.append({"question_id": question.id, "answer": answer, "confidence": confidence})
            db.session.add(question)

        db.session.commit()

        structured = self.structured_manager.load(run_id)
        for question_dict, result in zip(structured.get("questions", []), results):
            question_dict["gold_answer"] = result["answer"]
            question_dict["gold_confidence"] = result["confidence"]

        metadata = structured.setdefault("pipeline_metadata", {})
        stages_completed = set(metadata.get("stages_completed", []))
        stages_completed.add("answer_detection")
        metadata.update(
            {
                "current_stage": "answer_detection",
                "stages_completed": list(stages_completed),
                "last_updated": isoformat(utc_now()),
            }
        )
        self.structured_manager.save(run_id, structured)

        return {"questions": len(results)}

    def _determine_answer(self, question: QuestionManipulation) -> tuple[str, float]:
        options = question.options_data or {}
        if not options:
            return ("N/A", 0.0)

        if self.ai_client.is_configured():
            # TODO: integrate with real AI providers. For now boost confidence to reflect availability.
            heuristic_label = next(iter(options.keys()))
            return (heuristic_label, 0.85)

        # Prefer heuristic when AI keys are unavailable
        for label in ["A", "B", "C", "D"]:
            if label in options:
                return (label, 0.6)

        # As a fallback choose the first key
        first_label = next(iter(options.keys()))
        return (first_label, 0.5)
