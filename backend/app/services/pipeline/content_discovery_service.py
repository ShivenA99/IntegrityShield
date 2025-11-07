from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

from ...extensions import db
from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
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
        metadata = structured.get("pipeline_metadata", {}) or {}

        existing_manipulations = {
            str(manip.question_number): manip
            for manip in QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
        }
        smart_substitution_completed = "smart_substitution" in set(metadata.get("stages_completed", []) or [])
        has_existing_mappings = any((manip.substring_mappings or []) for manip in existing_manipulations.values())
        preserve_manipulations = bool(existing_manipulations) and smart_substitution_completed

        if preserve_manipulations and not has_existing_mappings:
            # If smart substitution recorded completion but no mappings were stored, fall back to reset mode
            preserve_manipulations = False

        # Prefer AI questions produced in smart_reading (data_extraction pipeline results)
        ai_questions: List[Dict[str, Any]] = list(structured.get("ai_questions") or [])

        if ai_questions:
            # If ai_questions available, use them as the source of truth
            self.logger.info(
                f"Using {len(ai_questions)} AI questions from smart_reading (data_extraction pipeline) as source of truth",
                run_id=run_id,
            )
            questions = ai_questions
        else:
            self.logger.warning(
                "AI extraction returned no questions; falling back to heuristic detection",
                run_id=run_id,
            )
            questions = self._fallback_question_detection(elements)

        # Normalize and ensure required fields
        for i, question in enumerate(questions):
            # Handle both old format and data_extraction format
            # data_extraction format: question_number is int, needs to be converted to string
            q_number = question.get("q_number") or question.get("question_number")
            if q_number is not None:
                question["q_number"] = str(q_number)
            else:
                question["q_number"] = str(i + 1)
            
            # Ensure question_number is also set (for compatibility)
            question.setdefault("question_number", question["q_number"])
            
            question.setdefault("question_type", question.get("question_type") or "mcq_single")
            if not question.get("stem_text"):
                question["stem_text"] = f"Question {i + 1}"
            question.setdefault("options", question.get("options") or {})
            
            # Normalize positioning data from data_extraction format
            positioning = question.get("positioning", {})
            if positioning:
                # Ensure stem_bbox is set from positioning.bbox or positioning.stem_bbox
                if not question.get("stem_bbox"):
                    question["stem_bbox"] = positioning.get("stem_bbox") or positioning.get("bbox")
                
                # Ensure stem_spans is set from positioning.stem_spans
                if not question.get("stem_spans"):
                    question["stem_spans"] = positioning.get("stem_spans", [])

        # Persist question manipulations (replace all for this run)
        if preserve_manipulations:
            self.logger.info(
                "Preserving existing manipulations during content discovery",
                run_id=run_id,
                questions=len(existing_manipulations),
            )
            updated_manipulations = {}
            new_question_numbers = set()

            for question in questions:
                q_number = str(question.get("q_number") or question.get("question_number") or "").strip()
                if not q_number:
                    continue
                new_question_numbers.add(q_number)
                existing = existing_manipulations.get(q_number)

                if existing:
                    existing.question_type = str(question.get("question_type", existing.question_type or "mcq_single"))
                    existing.original_text = str(question.get("stem_text") or existing.original_text or "")
                    existing.options_data = question.get("options", existing.options_data or {})
                    positioning = question.get("positioning") or {}
                    if positioning:
                        existing.stem_position = positioning
                    updated_manipulations[q_number] = existing
                    db.session.add(existing)
                else:
                    manipulation = QuestionManipulation(
                        pipeline_run_id=run_id,
                        question_number=q_number,
                        question_type=str(question.get("question_type", "multiple_choice")),
                        original_text=str(question.get("stem_text") or f"Question {q_number}"),
                        options_data=question.get("options", {}),
                        ai_model_results={},
                    )
                    db.session.add(manipulation)
                    updated_manipulations[q_number] = manipulation

            for q_number, manipulation in existing_manipulations.items():
                if q_number not in new_question_numbers:
                    self.logger.info(
                        "Removing stale manipulation after content discovery",
                        run_id=run_id,
                        question_number=q_number,
                    )
                    db.session.delete(manipulation)

            db.session.commit()
            existing_manipulations = updated_manipulations
        else:
            if existing_manipulations:
                self.logger.info(
                    "Resetting manipulations for content discovery",
                    run_id=run_id,
                    previous_questions=len(existing_manipulations),
                )
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
            existing_manipulations = {
                str(manip.question_number): manip
                for manip in QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
            }

        # Build a minimal question_index to tie questions to geometry for later rendering
        # Prefer positioning from AI extraction if available
        question_index: List[Dict[str, Any]] = []
        span_index_available = bool(structured.get("pymupdf_span_index"))

        def normalize_bbox(value: Any) -> Optional[List[float]]:
            if isinstance(value, (list, tuple)) and len(value) == 4:
                try:
                    return [float(value[i]) for i in range(4)]
                except (TypeError, ValueError):
                    return None
            return None
        for q in questions:
            pos_raw = q.get("positioning") or {}
            positioning = dict(pos_raw)

            # Handle stem_spans from multiple sources (data_extraction format or old format)
            stem_spans_raw = (
                q.get("stem_spans")
                or positioning.get("stem_spans")
                or positioning.get("span_ids")
            )
            if isinstance(stem_spans_raw, list):
                stem_spans = [str(span_id) for span_id in stem_spans_raw if span_id]
            elif isinstance(stem_spans_raw, str):
                stem_spans = [stem_spans_raw]
            else:
                stem_spans = []

            # Handle stem_bbox from multiple sources
            # data_extraction format may have stem_bbox directly on question or in positioning
            stem_bbox = normalize_bbox(q.get("stem_bbox"))
            if stem_bbox is None:
                stem_bbox = normalize_bbox(positioning.get("stem_bbox"))
            if stem_bbox is None:
                stem_bbox = normalize_bbox(positioning.get("bbox"))

            if stem_bbox is not None:
                positioning["bbox"] = stem_bbox

            if stem_spans:
                positioning.setdefault("stem_spans", stem_spans)
                positioning.setdefault("span_ids", stem_spans)
            elif span_index_available:
                self.logger.warning(
                    "AI extraction did not provide stem spans",
                    run_id=run_id,
                    question=q.get("q_number") or q.get("question_number"),
                )

            q["positioning"] = positioning
            q["stem_bbox"] = stem_bbox
            q["stem_spans"] = stem_spans

            if preserve_manipulations:
                q_number = str(q.get("q_number") or q.get("question_number") or "").strip()
                existing = existing_manipulations.get(q_number)
                if existing:
                    substring_mappings = existing.substring_mappings or []
                    if substring_mappings:
                        manip_payload = {
                            "method": existing.manipulation_method or "smart_substitution",
                            "substring_mappings": substring_mappings,
                            "effectiveness_score": existing.effectiveness_score,
                            "auto_generate_status": "prefilled",
                        }
                    else:
                        manip_payload = {
                            "method": existing.manipulation_method or "smart_substitution",
                            "substring_mappings": [],
                            "effectiveness_score": existing.effectiveness_score,
                            "auto_generate_status": "pending",
                        }

                    q["manipulation"] = manip_payload

                    stem_position = existing.stem_position or {}
                    if stem_position:
                        q.setdefault("positioning", {})
                        for key, value in stem_position.items():
                            if key not in q["positioning"] or q["positioning"][key] in (None, [], {}):
                                q["positioning"][key] = value
                        stem_bbox_existing = stem_position.get("bbox")
                        if stem_bbox_existing and q.get("stem_bbox") is None:
                            try:
                                q["stem_bbox"] = [float(v) for v in stem_bbox_existing]
                            except (TypeError, ValueError):
                                q["stem_bbox"] = stem_bbox_existing
                        stem_spans_existing = (
                            stem_position.get("stem_spans")
                            or stem_position.get("span_ids")
                            or []
                        )
                        if stem_spans_existing and not q.get("stem_spans"):
                            q["stem_spans"] = [str(span_id) for span_id in stem_spans_existing if span_id]

            entry = {
                "q_number": str(q.get("q_number")),
                "page": positioning.get("page"),
                "stem": {
                    "text": q.get("stem_text", ""),
                    "bbox": stem_bbox,
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
                "positioning": positioning,
            }

            if stem_spans:
                entry["stem"]["spans"] = stem_spans
                entry["stem_spans"] = stem_spans

            if stem_bbox is not None:
                entry["stem_bbox"] = stem_bbox

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
        """Simple fallback question detection when AI extraction fails."""
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
