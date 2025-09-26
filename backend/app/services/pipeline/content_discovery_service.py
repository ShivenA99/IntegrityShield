from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List

from ...extensions import db
from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.ai_clients.gpt5_fusion_client import GPT5FusionClient
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now


class ContentDiscoveryService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.structured_manager = StructuredDataManager()

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._discover_questions, run_id)

    def _discover_questions(self, run_id: str) -> Dict[str, Any]:
        structured = self.structured_manager.load(run_id)
        elements = structured.get("content_elements", [])

        # Use GPT-5 fusion to analyze elements and generate questions with manipulation targets
        fusion_client = GPT5FusionClient()

        if fusion_client.is_configured():
            self.logger.info("Using GPT-5 fusion for question analysis", run_id=run_id)

            # Analyze elements with GPT-5
            ai_result = fusion_client.analyze_elements_for_questions(elements, run_id)

            if ai_result.error:
                self.logger.warning(f"GPT-5 fusion failed, falling back to basic detection: {ai_result.error}", run_id=run_id)
                questions = self._fallback_question_detection(elements)
            else:
                questions = ai_result.questions
                self.logger.info(f"GPT-5 fusion detected {len(questions)} questions with manipulation targets", run_id=run_id)
        else:
            self.logger.warning("GPT-5 fusion not configured, using fallback detection", run_id=run_id)
            questions = self._fallback_question_detection(elements)

        # Convert GPT-5 analysis to our database format
        for i, question in enumerate(questions):
            # Ensure required fields for database
            question.setdefault("q_number", str(i + 1))
            question.setdefault("question_type", "mcq_single")
            question.setdefault("stem_text", f"Question {i + 1}")
            question.setdefault("options", {})

        # Persist question manipulations
        QuestionManipulation.query.filter_by(pipeline_run_id=run_id).delete()
        db.session.commit()

        for question in questions:
            manipulation = QuestionManipulation(
                pipeline_run_id=run_id,
                question_number=question["q_number"],
                question_type=question.get("question_type", "multiple_choice"),
                original_text=question["stem_text"],
                options_data=question.get("options", {}),
                ai_model_results={}
            )
            db.session.add(manipulation)

        db.session.commit()

        structured["questions"] = questions
        metadata = structured.setdefault("pipeline_metadata", {})
        stages_completed = set(metadata.get("stages_completed", []))
        stages_completed.add("content_discovery")
        metadata.update(
            {
                "current_stage": "content_discovery",
                "stages_completed": list(stages_completed),
                "last_updated": isoformat(utc_now()),
            }
        )
        self.structured_manager.save(run_id, structured)

        return {"questions_detected": len(questions)}

    def _fallback_question_detection(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Simple fallback question detection when GPT-5 fusion is not available."""
        text_elements = [elem for elem in elements if elem.get("type") == "text"]
        text_elements.sort(key=lambda e: (e.get("bbox", [0, 0])[1], e.get("bbox", [0, 0])[0]))

        questions = []
        for i, element in enumerate(text_elements):
            content = element.get("content", "").strip()
            if re.match(r"^Question\s*-\s*\d+", content):
                questions.append({
                    "question_id": f"fallback_q{len(questions) + 1}",
                    "q_number": str(len(questions) + 1),
                    "question_type": "mcq_single",
                    "stem_text": content,
                    "options": {},
                    "manipulation_targets": [],  # No targets for fallback mode
                    "confidence": 0.5
                })

        return questions
