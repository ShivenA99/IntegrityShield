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

        # Prefer AI questions produced in smart_reading (vision/fusion results)
        ai_questions: List[Dict[str, Any]] = list(structured.get("ai_questions") or [])

        # Use GPT-5 fusion to analyze elements only if ai_questions are missing
        fusion_client = GPT5FusionClient()

        if not ai_questions:
            if fusion_client.is_configured():
                self.logger.info("Using GPT-5 fusion for question analysis", run_id=run_id)
                ai_result = fusion_client.analyze_elements_for_questions(elements, run_id)
                if ai_result.error:
                    self.logger.warning(
                        f"GPT-5 fusion failed, falling back to basic detection: {ai_result.error}",
                        run_id=run_id,
                    )
                    questions = self._fallback_question_detection(elements)
                else:
                    questions = ai_result.questions
                    self.logger.info(
                        f"GPT-5 fusion detected {len(questions)} questions with manipulation targets",
                        run_id=run_id,
                    )
            else:
                self.logger.warning("GPT-5 fusion not configured, using fallback detection", run_id=run_id)
                questions = self._fallback_question_detection(elements)
        else:
            # If ai_questions available, use them as the source of truth
            self.logger.info(
                f"Using {len(ai_questions)} AI questions from smart_reading as source of truth",
                run_id=run_id,
            )
            questions = ai_questions

        # Normalize and ensure required fields
        for i, question in enumerate(questions):
            question.setdefault("q_number", str(question.get("question_number") or i + 1))
            question.setdefault("question_type", question.get("question_type") or "mcq_single")
            if not question.get("stem_text"):
                question["stem_text"] = f"Question {i + 1}"
            question.setdefault("options", question.get("options") or {})

        # Persist question manipulations (replace all for this run)
        QuestionManipulation.query.filter_by(pipeline_run_id=run_id).delete()
        db.session.commit()

        for question in questions:
            manipulation = QuestionManipulation(
                pipeline_run_id=run_id,
                question_number=str(question["q_number"]),
                question_type=str(question.get("question_type", "multiple_choice")),
                original_text=str(question["stem_text"]),
                options_data=question.get("options", {}),
                ai_model_results={},
            )
            db.session.add(manipulation)

        db.session.commit()

        # Build a minimal question_index to tie questions to geometry for later rendering
        # Prefer positioning from AI extraction if available
        question_index: List[Dict[str, Any]] = []
        for q in questions:
            pos = (q.get("positioning") or {})
            entry = {
                "q_number": str(q.get("q_number")),
                "page": pos.get("page"),
                "stem": {
                    "text": q.get("stem_text", ""),
                    "bbox": pos.get("bbox"),
                },
                "options": {
                    k: {"text": v}
                    for k, v in (q.get("options") or {}).items()
                },
                "provenance": {
                    "sources_detected": q.get("sources_detected") or [
                        (structured.get("ai_extraction", {}).get("source") or "unknown")
                    ]
                },
            }
            question_index.append(entry)

        # Update structured data
        structured["questions"] = questions
        structured["question_index"] = question_index
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
                questions.append(
                    {
                        "question_id": f"fallback_q{len(questions) + 1}",
                        "q_number": str(len(questions) + 1),
                        "question_type": "mcq_single",
                        "stem_text": content,
                        "options": {},
                        "manipulation_targets": [],  # No targets for fallback mode
                        "confidence": 0.5,
                        "positioning": {"page": element.get("page")},
                    }
                )

        return questions
