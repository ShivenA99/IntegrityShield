from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import selectinload

from ...models import PipelineRun, QuestionManipulation
from ...utils.exceptions import ResourceNotFound
from ...utils.storage_paths import detection_report_directory, run_directory
from ...utils.time import isoformat, utc_now
from ..data_management.structured_data_manager import StructuredDataManager


@dataclass
class MappingInsight:
    original: Optional[str]
    replacement: Optional[str]
    context: Optional[str]
    validated: bool
    target_wrong_answer: Optional[str]
    deviation_score: Optional[float]
    confidence: Optional[float]
    validation_reason: Optional[str]


class DetectionReportService:
    """Generate an auditable detection report for downstream cheating evaluation."""

    SUBJECTIVE_TYPES = {
        "short_answer",
        "long_answer",
        "subjective",
        "essay",
        "code",
        "programming",
        "open_response",
        "constructed_response",
    }

    REQUIRED_STAGES = {"smart_substitution"}

    def __init__(self) -> None:
        self.structured_manager = StructuredDataManager()

    def generate(self, run_id: str) -> Dict[str, Any]:
        run = (
            PipelineRun.query.options(
                selectinload(PipelineRun.questions),
                selectinload(PipelineRun.stages),
            )
            .filter_by(id=run_id)
            .one_or_none()
        )
        if not run:
            raise ResourceNotFound(f"Pipeline run {run_id} not found")

        self._guard_required_stages(run)

        if not run.questions:
            raise ValueError("No questions available to build the detection report.")

        structured = self.structured_manager.load(run_id) or {}
        structured_question_index = self._index_structured_questions(structured.get("questions", []))

        generated_at = isoformat(utc_now())
        detection_dir = detection_report_directory(run_id)
        report_path = detection_dir / "detection_report.json"

        compiled_questions: List[Dict[str, Any]] = []
        total_mappings = 0
        validated_mappings = 0
        questions_with_mappings = 0
        high_risk_questions = 0
        missing_mapping_questions = 0
        target_labels_counter: Counter[str] = Counter()

        for question in sorted(run.questions, key=self._question_sort_key):
            question_number = str(question.question_number or question.id)
            structured_info = structured_question_index.get(question_number, {})
            options = self._normalize_options(question.options_data, structured_info)
            option_lookup = {self._normalize_label(opt["label"]): opt for opt in options if opt.get("label")}
            gold_label = self._normalize_label(question.gold_answer or structured_info.get("gold_answer"))
            gold_entry = option_lookup.get(gold_label)

            mappings = list(question.substring_mappings or [])
            mapping_insights, mapping_stats = self._compile_mappings(mappings)

            total_mappings += mapping_stats["total"]
            validated_mappings += mapping_stats["validated"]
            if mapping_stats["total"] > 0:
                questions_with_mappings += 1
            else:
                missing_mapping_questions += 1

            target_labels = mapping_stats["target_labels"]
            for label in target_labels:
                target_labels_counter[label] += 1

            replacements = mapping_stats["replacements"]
            target_texts = self._resolve_target_texts(target_labels, replacements, option_lookup)

            risk_level = self._assess_risk(mapping_stats, bool(options))
            if risk_level == "high":
                high_risk_questions += 1

            compiled_questions.append(
                {
                    "question_number": question_number,
                    "question_type": question.question_type,
                    "stem_text": self._resolve_question_text(question, structured_info),
                    "options": options,
                    "is_subjective": self._is_subjective(question.question_type, options),
                    "subjective_reference_answer": self._resolve_subjective_reference(structured_info, question),
                    "gold_answer": {
                        "label": gold_label,
                        "text": gold_entry["text"] if gold_entry else structured_info.get("gold_answer") or question.gold_answer,
                    },
                    "target_answer": {
                        "labels": sorted(target_labels),
                        "texts": target_texts,
                        "raw_replacements": sorted(replacements),
                    },
                    "mappings": [insight.__dict__ for insight in mapping_insights],
                    "risk_level": risk_level,
                    "risk_factors": mapping_stats,
                }
            )

        summary = {
            "total_questions": len(run.questions),
            "questions_with_mappings": questions_with_mappings,
            "questions_missing_mappings": missing_mapping_questions,
            "validated_mappings": validated_mappings,
            "total_mappings": total_mappings,
            "high_risk_questions": high_risk_questions,
            "target_label_distribution": [
                {"label": label, "count": count}
                for label, count in target_labels_counter.most_common()
            ],
        }

        result_payload = {
            "run_id": run_id,
            "report_type": "detection",
            "generated_at": generated_at,
            "summary": summary,
            "questions": compiled_questions,
        }

        report_path.write_text(
            json.dumps(result_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        relative_path = str(report_path.resolve().relative_to(run_directory(run_id)))

        manipulation_results = structured.setdefault("manipulation_results", {})
        detection_payload = {
            **result_payload,
            "file_path": str(report_path),
            "relative_path": relative_path,
            "status": "completed",
        }
        manipulation_results["detection_report"] = detection_payload

        artifacts = manipulation_results.setdefault("artifacts", {})
        artifacts["detection_report"] = {"json": relative_path}

        reports_section = structured.setdefault("reports", {})
        reports_section["detection"] = {
            "generated_at": generated_at,
            "summary": summary,
            "artifact": relative_path,
            "status": "completed",
        }

        self.structured_manager.save(run_id, structured)

        return {
            **result_payload,
            "output_files": {"json": relative_path},
        }

    def _guard_required_stages(self, run: PipelineRun) -> None:
        stage_status = {stage.stage_name: stage.status for stage in run.stages}
        missing = sorted(stage for stage in self.REQUIRED_STAGES if stage_status.get(stage) != "completed")
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(
                f"Cannot generate detection report until prerequisite stages are completed ({missing_list})."
            )

    def _compile_mappings(self, mappings: List[Dict[str, Any]]) -> Tuple[List[MappingInsight], Dict[str, Any]]:
        insights: List[MappingInsight] = []
        total = 0
        validated = 0
        target_labels: set[str] = set()
        replacements: set[str] = set()
        deviations: List[float] = []
        confidences: List[float] = []

        for mapping in mappings:
            total += 1
            is_validated = bool(mapping.get("validated")) or bool(mapping.get("validation", {}).get("is_valid"))
            if is_validated:
                validated += 1

            # Check both target_wrong_answer and target_option fields
            target_label = self._normalize_label(
                mapping.get("target_wrong_answer") or mapping.get("target_option")
            )
            if target_label:
                target_labels.add(target_label)

            replacement = mapping.get("replacement")
            if replacement:
                replacements.add(str(replacement))

            # Extract deviation_score from mapping (check both direct field and validation object)
            deviation = mapping.get("deviation_score") or mapping.get("validation", {}).get("deviation_score")
            if isinstance(deviation, (int, float)):
                deviations.append(float(deviation))

            confidence = mapping.get("confidence") or mapping.get("validation", {}).get("confidence")
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))

            # Extract target_wrong_answer from either field
            target_wrong_answer_value = mapping.get("target_wrong_answer") or mapping.get("target_option")
            insights.append(
                MappingInsight(
                    original=self._safe_strip(mapping.get("original")),
                    replacement=self._safe_strip(mapping.get("replacement")),
                    context=mapping.get("context"),
                    validated=is_validated,
                    target_wrong_answer=self._normalize_label(target_wrong_answer_value),
                    deviation_score=float(deviation) if isinstance(deviation, (int, float)) else None,
                    confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                    validation_reason=(
                        mapping.get("validation", {}).get("reasoning")
                        or mapping.get("validation_reasoning")
                    ),
                )
            )

        # For deviation_score: use the first validated mapping's score, or max if multiple
        # Most questions have one mapping, so averaging doesn't add value
        # If multiple mappings, use the maximum deviation (most effective attack)
        question_deviation_score = None
        if deviations:
            if len(deviations) == 1:
                question_deviation_score = deviations[0]
            else:
                # Multiple mappings: use the maximum deviation (most effective attack)
                question_deviation_score = max(deviations)
        
        average_confidence = sum(confidences) / len(confidences) if confidences else None

        stats = {
            "total": total,
            "validated": validated,
            "target_labels": sorted(target_labels),
            "replacements": sorted(replacements),
            "average_deviation_score": question_deviation_score,  # Actually the primary/max deviation score
            "average_confidence": average_confidence,
        }

        return insights, stats

    @staticmethod
    def _index_structured_questions(questions: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        lookup: Dict[str, Dict[str, Any]] = {}
        for entry in questions or []:
            number = str(
                entry.get("question_number")
                or entry.get("question_no")
                or entry.get("q_number")
                or entry.get("number")
                or ""
            )
            if number:
                lookup[number] = entry
        return lookup

    @staticmethod
    def _question_sort_key(question: QuestionManipulation) -> Tuple[int, str]:
        seq = question.sequence_index if question.sequence_index is not None else 10**6
        return (seq, str(question.question_number or question.id))

    @staticmethod
    def _resolve_question_text(question: QuestionManipulation, structured_info: Dict[str, Any]) -> str:
        return (
            structured_info.get("stem_text")
            or structured_info.get("question_text")
            or question.original_text
        )

    def _resolve_subjective_reference(self, structured_info: Dict[str, Any], question: QuestionManipulation) -> Optional[str]:
        if not self._is_subjective(question.question_type, structured_info.get("options") or []):
            return None
        subjective_sources = [
            structured_info.get("gold_answer"),
            structured_info.get("reference_answer"),
            structured_info.get("model_answer"),
            structured_info.get("expected_answer"),
            question.gold_answer,
        ]
        for value in subjective_sources:
            cleaned = self._safe_strip(value)
            if cleaned:
                return cleaned
        return None

    def _is_subjective(self, question_type: Optional[str], options: Iterable[Dict[str, Any]]) -> bool:
        if question_type and question_type.lower() in self.SUBJECTIVE_TYPES:
            return True
        options_list = list(options or [])
        if options_list:
            return False
        return False

    def _normalize_options(self, options_data: Any, structured_info: Dict[str, Any]) -> List[Dict[str, str]]:
        if not options_data and structured_info.get("options"):
            options_data = structured_info["options"]

        normalized: List[Dict[str, str]] = []
        if isinstance(options_data, dict):
            for key, value in options_data.items():
                normalized.append({"label": str(key), "text": str(value)})
        elif isinstance(options_data, list):
            for entry in options_data:
                if isinstance(entry, dict):
                    label = entry.get("label") or entry.get("option") or entry.get("id")
                    text = entry.get("text") or entry.get("value") or entry.get("content")
                    normalized.append(
                        {
                            "label": str(label or len(normalized) + 1),
                            "text": str(text or ""),
                        }
                    )
                else:
                    normalized.append({"label": str(len(normalized) + 1), "text": str(entry)})
        elif isinstance(options_data, str):
            parts = [part.strip() for part in options_data.split("\n") if part.strip()]
            normalized = [{"label": chr(65 + idx), "text": part} for idx, part in enumerate(parts)]

        return normalized

    def _resolve_target_texts(
        self,
        labels: Iterable[str],
        replacements: Iterable[str],
        option_lookup: Dict[Optional[str], Dict[str, str]],
    ) -> List[str]:
        texts: List[str] = []
        for label in labels:
            entry = option_lookup.get(label)
            if entry:
                candidate = self._safe_strip(entry.get("text"))
                if candidate:
                    texts.append(candidate)
        if texts:
            return texts
        return [self._safe_strip(value) for value in replacements if self._safe_strip(value)]

    @staticmethod
    def _normalize_label(label: Any) -> Optional[str]:
        if label is None:
            return None
        if isinstance(label, (int, float)):
            return str(label)
        cleaned = str(label).strip()
        if cleaned.endswith("."):
            cleaned = cleaned[:-1]
        cleaned = cleaned.strip()
        if not cleaned:
            return None
        return cleaned.upper()

    @staticmethod
    def _safe_strip(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _assess_risk(mapping_stats: Dict[str, Any], has_options: bool) -> str:
        """
        Assess risk level based on mapping statistics.
        
        Note: High deviation_score means the attack is EFFECTIVE (successfully changes the answer),
        which translates to HIGH RISK of cheating. So high deviation = high risk.
        """
        total = mapping_stats.get("total", 0)
        validated = mapping_stats.get("validated", 0)
        average_deviation = mapping_stats.get("average_deviation_score")
        if total == 0:
            return "skipped"
        if validated == 0:
            return "needs-review"
        # High deviation_score (>= 0.7) = attack works well = HIGH RISK of successful cheating
        # Medium deviation_score (0.5-0.7) = moderate attack effectiveness = MEDIUM RISK
        # Low deviation_score (< 0.5) = attack less effective = LOW RISK
        if isinstance(average_deviation, (int, float)):
            if average_deviation >= 0.7:
                return "high"
            elif average_deviation >= 0.5:
                return "medium"
            else:
                return "low"
        # Fallback: if no deviation score but has target labels, mark as medium
        if has_options and mapping_stats.get("target_labels"):
            return "medium"
        return "low"
