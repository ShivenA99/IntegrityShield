from __future__ import annotations

import random
from typing import Dict, Iterable, List

from flask import current_app

from ...extensions import db
from ...models import AIModelResult, PipelineRun, QuestionManipulation
from ...utils.exceptions import ResourceNotFound
from ...utils.logging import get_logger
from ..integration.external_api_client import ExternalAIClient


class MultiModelTester:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.client = ExternalAIClient()

    def test_question(self, run_id: str, question_id: int, models: Iterable[str] | None = None) -> Dict[str, Dict]:
        question = QuestionManipulation.query.filter_by(pipeline_run_id=run_id, id=question_id).first()
        if not question:
            raise ResourceNotFound("Question manipulation not found")

        pipeline_run = PipelineRun.query.get(run_id)
        configured_models = list(models or pipeline_run.pipeline_config.get("ai_models", []))
        if not configured_models:
            configured_models = current_app.config.get("PIPELINE_DEFAULT_MODELS", [])

        results: Dict[str, Dict] = {}

        for model_name in configured_models:
            simulated = self._simulate_model_response(question, model_name)
            ai_record = AIModelResult(
                pipeline_run_id=run_id,
                question_id=question.id,
                model_name=model_name,
                original_answer=simulated["original_answer"],
                original_confidence=simulated["original_confidence"],
                manipulated_answer=simulated["manipulated_answer"],
                manipulated_confidence=simulated["manipulated_confidence"],
                was_fooled=simulated["was_fooled"],
                response_time_ms=simulated["response_time_ms"],
                api_cost_cents=simulated["api_cost_cents"],
                full_response=simulated,
            )
            db.session.add(ai_record)
            results[model_name] = simulated

        question.ai_model_results = results
        question.effectiveness_score = self._calculate_effectiveness(results.values())
        db.session.add(question)
        db.session.commit()

        return results

    def _simulate_model_response(self, question: QuestionManipulation, model_name: str) -> Dict:
        mappings = question.substring_mappings or []
        manipulation_strength = min(1.0, len(mappings) / 5 or 0.2)
        fooled_probability = 0.3 + manipulation_strength * 0.6
        was_fooled = random.random() < fooled_probability

        original_answer = question.gold_answer or "A"
        manipulated_answer = question.gold_answer if not was_fooled else "B"
        confidence_drop = manipulation_strength * 0.4

        return {
            "model": model_name,
            "original_answer": original_answer,
            "original_confidence": round(0.9 - confidence_drop / 2, 2),
            "manipulated_answer": manipulated_answer,
            "manipulated_confidence": round(0.9 - confidence_drop - 0.1, 2),
            "was_fooled": was_fooled,
            "response_time_ms": int(800 + random.random() * 400),
            "api_cost_cents": round(10 + random.random() * 6, 2),
        }

    def _calculate_effectiveness(self, records: Iterable[Dict]) -> float:
        total = 0
        fooled = 0
        for record in records:
            total += 1
            if record.get("was_fooled"):
                fooled += 1
        return fooled / total if total else 0.0
