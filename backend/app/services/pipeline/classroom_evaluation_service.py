from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean, median
from typing import Any, Dict, Iterable, List

from sqlalchemy.orm import selectinload

from ...extensions import db
from ...models import AnswerSheetRun, ClassroomEvaluation
from ...utils.exceptions import ResourceNotFound
from ...utils.storage_paths import classroom_evaluation_artifact, run_directory
from ...utils.time import isoformat, utc_now


class ClassroomEvaluationService:
    """Aggregate student answer sheet datasets into classroom-level cheating insights."""

    SCORE_BUCKETS = [
        (0, 25),
        (25, 50),
        (50, 75),
        (75, 90),
        (90, 101),
    ]

    def evaluate(self, run_id: str, classroom_id: int, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        classroom: AnswerSheetRun | None = (
            AnswerSheetRun.query.options(
                selectinload(AnswerSheetRun.students),
                selectinload(AnswerSheetRun.records),
            )
            .filter_by(pipeline_run_id=run_id, id=classroom_id)
            .one_or_none()
        )

        if not classroom:
            raise ResourceNotFound(f"Classroom dataset {classroom_id} not found for run {run_id}")

        if not classroom.students:
            raise ValueError("Cannot evaluate classroom without generated or imported students.")

        config = payload or {}
        records_by_student = self._group_records_by_student(classroom.records)

        student_metrics = [
            self._build_student_metric(student, records_by_student.get(student.id, []))
            for student in classroom.students
        ]

        summary = self._build_summary(student_metrics)
        detailed_payload = {
            "classroom_id": classroom.id,
            "classroom_key": classroom.classroom_key,
            "classroom_label": classroom.classroom_label,
            "attacked_pdf_method": classroom.attacked_pdf_method,
            "evaluated_at": isoformat(utc_now()),
            "summary": summary,
            "students": student_metrics,
        }

        json_path = classroom_evaluation_artifact(
            run_id,
            classroom.classroom_key or f"classroom-{classroom.id}",
            "evaluation.json",
        )
        json_path.write_text(json.dumps(detailed_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        relative_path = str(json_path.resolve().relative_to(run_directory(run_id)))

        evaluation = classroom.evaluation or ClassroomEvaluation(
            answer_sheet_run_id=classroom.id,
            pipeline_run_id=run_id,
        )
        evaluation.status = "completed"
        evaluation.summary = summary
        evaluation.artifacts = {"json": relative_path}
        evaluation.evaluation_config = config
        evaluation.completed_at = utc_now()

        classroom.status = "ready"
        classroom.last_evaluated_at = evaluation.completed_at

        db.session.add(evaluation)
        db.session.add(classroom)
        db.session.commit()

        return {
            "classroom_id": classroom.id,
            "summary": summary,
            "students": student_metrics,
            "artifacts": evaluation.artifacts,
            "evaluation_config": evaluation.evaluation_config,
            "status": evaluation.status,
        }

    def _group_records_by_student(self, records: Iterable[Any]) -> Dict[int, List[Any]]:
        grouped: Dict[int, List[Any]] = defaultdict(list)
        for record in records:
            if record.student_id is None:
                continue
            grouped[record.student_id].append(record)
        return grouped

    def _build_student_metric(self, student: Any, records: List[Any]) -> Dict[str, Any]:
        total_questions = len(records)
        correct_answers = sum(1 for record in records if getattr(record, "is_correct", False))
        incorrect_answers = total_questions - correct_answers
        cheating_sources = defaultdict(int)
        for record in records:
            cheating_sources[str(record.cheating_source or "fair")] += 1

        score = float(student.score or 0.0)
        confidence_values = [float(record.confidence or 0.0) for record in records if record.confidence is not None]
        avg_confidence = mean(confidence_values) if confidence_values else None

        return {
            "student_id": student.id,
            "student_key": student.student_key,
            "display_name": student.display_name or student.student_key,
            "is_cheating": bool(student.is_cheating),
            "cheating_strategy": student.cheating_strategy,
            "copy_fraction": student.copy_fraction,
            "paraphrase_style": student.paraphrase_style,
            "score": score,
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "incorrect_answers": incorrect_answers,
            "cheating_source_counts": dict(cheating_sources),
            "average_confidence": avg_confidence,
            "metadata": student.metadata_json or {},
        }

    def _build_summary(self, students: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_students = len(students)
        cheating_students = sum(1 for student in students if student["is_cheating"])
        strategy_breakdown = defaultdict(int)
        scores = [student["score"] for student in students]

        for student in students:
            strategy_breakdown[str(student.get("cheating_strategy") or "fair")] += 1

        score_distribution = self._bucket_scores(scores)

        return {
            "total_students": total_students,
            "cheating_students": cheating_students,
            "cheating_rate": (cheating_students / total_students) if total_students else 0.0,
            "strategy_breakdown": dict(strategy_breakdown),
            "average_score": mean(scores) if scores else 0.0,
            "median_score": median(scores) if scores else 0.0,
            "score_distribution": score_distribution,
        }

    def _bucket_scores(self, scores: List[float]) -> List[Dict[str, Any]]:
        distribution: List[Dict[str, Any]] = []
        total = len(scores)
        for lower, upper in self.SCORE_BUCKETS:
            count = sum(1 for score in scores if lower <= score < upper)
            distribution.append(
                {
                    "label": f"{lower}-{upper if upper != 101 else 100}",
                    "count": count,
                    "fraction": (count / total) if total else 0.0,
                }
            )
        return distribution
