from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

from ...extensions import db
from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from .gold_answer_generation_service import GoldAnswerGenerationService


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

        existing_rows = (
            QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
            .order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
            .all()
        )
        existing_by_id = {row.id: row for row in existing_rows}
        existing_by_source = {row.source_identifier: row for row in existing_rows if row.source_identifier}
        existing_by_number = {str(row.question_number): row for row in existing_rows}

        smart_substitution_completed = "smart_substitution" in set(metadata.get("stages_completed", []) or [])
        has_existing_mappings = any((row.substring_mappings or []) for row in existing_rows)
        preserve_manipulations = bool(existing_rows) and smart_substitution_completed and has_existing_mappings

        def derive_source_identifier(question: Dict[str, Any], index: int) -> str:
            candidates = [
                question.get("source_identifier"),
                question.get("question_id"),
                question.get("source_id"),
                question.get("uid"),
            ]
            for candidate in candidates:
                if candidate:
                    return str(candidate)

            positioning = question.get("positioning") or {}
            span_ids = positioning.get("span_ids") or positioning.get("stem_spans") or question.get("stem_spans")
            if isinstance(span_ids, list) and span_ids:
                return f"span-{span_ids[0]}"
            if isinstance(span_ids, str):
                return f"span-{span_ids}"

            return f"auto-{index}"

        ai_questions: List[Dict[str, Any]] = list(structured.get("ai_questions") or [])

        if ai_questions:
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

        for i, question in enumerate(questions):
            q_number = question.get("q_number") or question.get("question_number")
            if q_number is not None:
                question["q_number"] = str(q_number)
            else:
                question["q_number"] = str(i + 1)

            question.setdefault("question_number", question["q_number"])
            question.setdefault("question_type", question.get("question_type") or "mcq_single")
            if not question.get("stem_text"):
                question["stem_text"] = f"Question {i + 1}"
            question.setdefault("options", question.get("options") or {})

            positioning = question.get("positioning", {})
            if positioning:
                if not question.get("stem_bbox"):
                    question["stem_bbox"] = positioning.get("stem_bbox") or positioning.get("bbox")
                if not question.get("stem_spans"):
                    question["stem_spans"] = positioning.get("stem_spans", [])

            question["sequence_index"] = i
            question["source_identifier"] = derive_source_identifier(question, i)

        if preserve_manipulations:
            self.logger.info(
                "Preserving existing manipulations during content discovery",
                run_id=run_id,
                questions=len(existing_rows),
            )
            updated_rows: List[QuestionManipulation] = []
            seen_ids: set[int] = set()

            for question in questions:
                sequence_index = int(question.get("sequence_index", len(updated_rows)))
                source_identifier = str(question.get("source_identifier") or f"auto-{sequence_index}")
                q_number = str(question.get("q_number") or question.get("question_number") or "").strip()

                existing = existing_by_source.get(source_identifier)
                if existing is None:
                    existing = existing_by_number.get(q_number)

                if existing:
                    existing.sequence_index = sequence_index
                    if source_identifier and existing.source_identifier != source_identifier:
                        existing.source_identifier = source_identifier
                    existing.question_type = str(question.get("question_type", existing.question_type or "mcq_single"))
                    existing.original_text = str(question.get("stem_text") or existing.original_text or "")
                    existing.options_data = question.get("options", existing.options_data or {})
                    if question.get("visual_elements") is not None:
                        existing.visual_elements = question.get("visual_elements")
                    positioning = question.get("positioning") or {}
                    if positioning:
                        existing.stem_position = positioning
                    db.session.add(existing)

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
                    question["manipulation"] = manip_payload
                    question["manipulation_id"] = existing.id
                    question["sequence_index"] = existing.sequence_index
                    question["source_identifier"] = existing.source_identifier

                    if existing.source_identifier:
                        existing_by_source[existing.source_identifier] = existing
                    if q_number:
                        existing_by_number[q_number] = existing

                    stem_position = existing.stem_position or {}
                    if stem_position:
                        question.setdefault("positioning", {})
                        for key, value in stem_position.items():
                            if key not in question["positioning"] or question["positioning"][key] in (None, [], {}):
                                question["positioning"][key] = value
                        stem_bbox_existing = stem_position.get("bbox")
                        if stem_bbox_existing and question.get("stem_bbox") is None:
                            try:
                                question["stem_bbox"] = [float(v) for v in stem_bbox_existing]
                            except (TypeError, ValueError):
                                question["stem_bbox"] = stem_bbox_existing
                        stem_spans_existing = (
                            stem_position.get("stem_spans")
                            or stem_position.get("span_ids")
                            or []
                        )
                        if stem_spans_existing and not question.get("stem_spans"):
                            question["stem_spans"] = [str(span_id) for span_id in stem_spans_existing if span_id]

                    updated_rows.append(existing)
                    seen_ids.add(existing.id)
                else:
                    manipulation = QuestionManipulation(
                        pipeline_run_id=run_id,
                        question_number=q_number or str(sequence_index + 1),
                        question_type=str(question.get("question_type", "mcq_single")),
                        original_text=str(question.get("stem_text") or f"Question {sequence_index + 1}"),
                        options_data=question.get("options", {}),
                        visual_elements=question.get("visual_elements"),
                        ai_model_results={},
                        sequence_index=sequence_index,
                        source_identifier=source_identifier,
                    )
                    db.session.add(manipulation)
                    db.session.flush()

                    question["manipulation"] = {
                        "method": manipulation.manipulation_method or "smart_substitution",
                        "substring_mappings": [],
                        "effectiveness_score": manipulation.effectiveness_score,
                        "auto_generate_status": "pending",
                    }
                    question["manipulation_id"] = manipulation.id
                    question["sequence_index"] = manipulation.sequence_index
                    question["source_identifier"] = manipulation.source_identifier

                    if manipulation.source_identifier:
                        existing_by_source[manipulation.source_identifier] = manipulation
                    if q_number:
                        existing_by_number[q_number] = manipulation

                    updated_rows.append(manipulation)
                    seen_ids.add(manipulation.id)

            for row in existing_rows:
                if row.id not in seen_ids:
                    self.logger.info(
                        "Removing stale manipulation after content discovery",
                        run_id=run_id,
                        question_number=row.question_number,
                    )
                    db.session.delete(row)

            db.session.commit()
            existing_rows = updated_rows
            existing_by_id = {row.id: row for row in existing_rows}
        else:
            if existing_rows:
                self.logger.info(
                    "Resetting manipulations for content discovery",
                    run_id=run_id,
                    previous_questions=len(existing_rows),
                )
            QuestionManipulation.query.filter_by(pipeline_run_id=run_id).delete()
            db.session.commit()

            new_rows: List[QuestionManipulation] = []
            for question in questions:
                sequence_index = int(question.get("sequence_index", len(new_rows)))
                source_identifier = str(question.get("source_identifier") or f"auto-{sequence_index}")
                manipulation = QuestionManipulation(
                    pipeline_run_id=run_id,
                    question_number=str(question["q_number"]),
                    question_type=str(question.get("question_type", "mcq_single")),
                    original_text=str(question["stem_text"]),
                    options_data=question.get("options", {}),
                    visual_elements=question.get("visual_elements"),
                    ai_model_results={},
                    sequence_index=sequence_index,
                    source_identifier=source_identifier,
                )
                db.session.add(manipulation)
                db.session.flush()

                question["manipulation"] = {
                    "method": manipulation.manipulation_method or "smart_substitution",
                    "substring_mappings": [],
                    "effectiveness_score": manipulation.effectiveness_score,
                    "auto_generate_status": "pending",
                }
                question["manipulation_id"] = manipulation.id
                question["sequence_index"] = manipulation.sequence_index
                question["source_identifier"] = manipulation.source_identifier

                new_rows.append(manipulation)

            db.session.commit()
            existing_rows = new_rows
            existing_by_id = {row.id: row for row in existing_rows}

        structured["questions"] = questions

        metadata = structured.setdefault("pipeline_metadata", metadata)
        total_questions = len(questions)
        satisfied_count = sum(
            1 for question in questions if GoldAnswerGenerationService.is_gold_answer_satisfied(question)
        )
        gold_progress = {
            "status": "completed" if satisfied_count == total_questions else "running",
            "total": total_questions,
            "completed": satisfied_count,
            "pending": max(total_questions - satisfied_count, 0),
            "updated_at": isoformat(utc_now()),
        }
        metadata["gold_generation"] = gold_progress
        self.structured_manager.save(run_id, structured)

        gold_generator = GoldAnswerGenerationService()
        needs_gold = satisfied_count < total_questions
        if needs_gold and not gold_generator.is_configured():
            raise ValueError(
                "Gold answer generation requires GPT-5 configuration. "
                "Set OPENAI_API_KEY and FAIRTESTAI_GOLD_ANSWER_MODEL to continue."
            )

        processed_updates: set[tuple[int | None, str | None]] = set()

        def _persist_question_update(update: Optional[Dict[str, Any]]) -> None:
            if not update:
                return
            manip_id = update.get("manipulation_id")
            key = (manip_id, update.get("gold_answer"))
            if key in processed_updates:
                return
            if manip_id and manip_id in existing_by_id:
                row = existing_by_id[manip_id]
                gold_answer = update.get("gold_answer")
                gold_conf = update.get("gold_confidence")
                changed = False
                if gold_answer and row.gold_answer != gold_answer:
                    row.gold_answer = gold_answer
                    changed = True
                if gold_conf is not None and row.gold_confidence != gold_conf:
                    row.gold_confidence = gold_conf
                    changed = True
                if changed:
                    db.session.add(row)
                    db.session.commit()
                    existing_by_id[manip_id] = row
            processed_updates.add(key)

        def _progress_update(payload: Dict[str, Any], question_update: Optional[Dict[str, Any]]) -> None:
            metadata["gold_generation"] = payload
            metadata["last_updated"] = isoformat(utc_now())
            if question_update:
                _persist_question_update(question_update)
            self.structured_manager.save(run_id, structured)

        gold_updates: List[Dict[str, Any]] = []
        if gold_generator.is_configured():
            try:
                structured, gold_updates = gold_generator.populate_gold_answers(
                    run_id,
                    structured,
                    progress_callback=_progress_update,
                )
                questions = structured.get("questions", questions)
                # Explicitly sync gold answers to ai_questions after generation completes
                gold_generator._sync_ai_questions(structured)
                # Ensure structured["questions"] updates are persisted
                self.structured_manager.save(run_id, structured)
            except Exception as exc:  # pragma: no cover - defensive logging
                self.logger.warning("Gold answer generation failed: %s", exc, run_id=run_id)
        for update in gold_updates or []:
            _persist_question_update(update)

        final_completed = sum(
            1 for question in structured.get("questions", questions)
            if GoldAnswerGenerationService.is_gold_answer_satisfied(question)
        )
        metadata["gold_generation"] = {
            **metadata.get("gold_generation", {}),
            "status": "completed" if final_completed == total_questions else metadata.get("gold_generation", {}).get("status", "partial"),
            "total": total_questions,
            "completed": final_completed,
            "pending": max(total_questions - final_completed, 0),
            "updated_at": isoformat(utc_now()),
        }

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

            manipulation_id = q.get("manipulation_id")
            manipulation_model = existing_by_id.get(manipulation_id) if manipulation_id else None

            entry = {
                "manipulation_id": manipulation_id,
                "sequence_index": q.get("sequence_index"),
                "source_identifier": q.get("source_identifier"),
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

            if manipulation_model is not None:
                entry["question_number"] = str(manipulation_model.question_number)

            if stem_spans:
                entry["stem"]["spans"] = stem_spans
                entry["stem_spans"] = stem_spans

            if stem_bbox is not None:
                entry["stem_bbox"] = stem_bbox

            question_index.append(entry)

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
