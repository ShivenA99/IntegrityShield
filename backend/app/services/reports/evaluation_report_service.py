from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from flask import current_app
from sqlalchemy.orm import selectinload

from ...models import PipelineRun
from ...utils.exceptions import ResourceNotFound
from ...utils.storage_paths import (
    evaluation_report_directory,
    resolve_run_relative_path,
    run_directory,
)
from ...utils.time import isoformat, utc_now
from ..data_management.structured_data_manager import StructuredDataManager
from .answer_scoring import AnswerScoringService
from .pdf_question_orchestrator import PDFQuestionEvaluator, QuestionPrompt


class EvaluationReportService:
    """Score attacked PDFs per variant and compare with detection targets."""

    REQUIRED_STAGES = {"smart_substitution", "pdf_creation"}

    def __init__(self) -> None:
        self.structured_manager = StructuredDataManager()
        self.scoring_service = AnswerScoringService()

    def generate(self, run_id: str, method: str | None = None) -> Dict[str, Any]:
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

        structured = self.structured_manager.load(run_id) or {}
        
        # Validate detection report exists FIRST (before expensive PDF evaluation)
        # This provides better error messages and avoids wasting time
        try:
            detection_reference = self._load_detection_reference(run_id, structured)
        except ValueError as exc:
            raise ValueError(
                f"Detection report is required for evaluation reports. {str(exc)}"
            )
        
        method_name = method or self._default_method(structured)
        if not method_name:
            raise ValueError("No attacked PDF available to evaluate. Generate PDFs first.")

        pdf_path = self._resolve_enhanced_pdf(run_id, structured, method_name)
        if not pdf_path or not pdf_path.exists():
            raise ValueError(f"Attacked PDF for method '{method_name}' not found.")

        prompts = current_app.config.get("LLM_REPORT_PROMPTS") or [
            "Answer the referenced assessment question using the attached PDF.",
        ]
        questions = self._build_question_prompts(run, structured)
        if not questions:
            raise ValueError("No questions available to generate an evaluation report.")

        evaluator = PDFQuestionEvaluator(prompts=prompts)
        evaluation = evaluator.evaluate(str(pdf_path), questions)

        # Detection reference already loaded above, reuse it
        vulnerability_reference = self._load_vulnerability_reference(run_id, structured)

        scored_questions = self._augment_answers(
            evaluation["questions"],
            detection_reference,
            vulnerability_reference,
        )
        summary = self._build_summary(scored_questions, vulnerability_reference)

        payload = {
            "run_id": run_id,
            "report_type": "evaluation",
            "method": method_name,
            "generated_at": isoformat(utc_now()),
            "questions": scored_questions,
            "summary": summary,
            "providers": evaluation["providers"],
            "context": {
                "detection": {
                    "generated_at": detection_reference.get("generated_at"),
                    "summary": detection_reference.get("summary"),
                },
                "vulnerability": {
                    "generated_at": (vulnerability_reference or {}).get("generated_at"),
                    "summary": (vulnerability_reference or {}).get("summary"),
                },
            },
        }

        directory = evaluation_report_directory(run_id, method_name)
        artifact_path = directory / f"evaluation_report_{method_name}.json"
        artifact_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        relative_path = str(artifact_path.resolve().relative_to(run_directory(run_id)))
        self._update_structured_data(run_id, payload, relative_path)

        return {
            **payload,
            "output_files": {"json": relative_path},
        }

    def _guard_required_stages(self, run: PipelineRun) -> None:
        stage_status = {stage.stage_name: stage.status for stage in run.stages}
        missing = [stage for stage in self.REQUIRED_STAGES if stage_status.get(stage) != "completed"]
        if missing:
            raise ValueError(
                "Evaluation report requires completed Smart Substitution and PDF Creation stages.",
            )

    def _default_method(self, structured: Dict[str, Any]) -> str | None:
        enhanced = (structured.get("manipulation_results") or {}).get("enhanced_pdfs") or {}
        if enhanced:
            return next(iter(enhanced.keys()))
        return None

    def _resolve_enhanced_pdf(self, run_id: str, structured: Dict[str, Any], method: str) -> Path | None:
        enhanced = (structured.get("manipulation_results") or {}).get("enhanced_pdfs") or {}
        entry = enhanced.get(method)
        if not entry:
            return None
        relative = entry.get("relative_path") or entry.get("path") or entry.get("file_path")
        if not relative:
            return None
        return resolve_run_relative_path(run_id, relative)

    def _build_question_prompts(self, run: PipelineRun, structured: Dict[str, Any]) -> List[QuestionPrompt]:
        structured_index = {
            str(entry.get("question_number") or entry.get("id")): entry for entry in (structured.get("questions") or [])
        }
        prompts: List[QuestionPrompt] = []
        for question in sorted(run.questions, key=lambda q: (q.sequence_index or 10**6, q.id)):
            number = str(question.question_number or question.id)
            structured_info = structured_index.get(number, {})
            prompts.append(
                QuestionPrompt(
                    question_id=question.id,
                    question_number=number,
                    question_text=structured_info.get("stem_text") or question.original_text,
                    question_type=question.question_type,
                    options=self._normalize_options(question.options_data, structured_info),
                    gold_answer=structured_info.get("gold_answer") or question.gold_answer,
                )
            )
        return prompts

    def _normalize_options(self, options_data: Any, structured_info: Dict[str, Any]) -> List[Dict[str, str]]:
        data = options_data or structured_info.get("options")
        normalized: List[Dict[str, str]] = []
        if isinstance(data, dict):
            for key, value in data.items():
                normalized.append({"label": str(key), "text": str(value)})
        elif isinstance(data, list):
            for entry in data:
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
        return normalized

    def _augment_answers(
        self,
        questions: List[Dict[str, Any]],
        detection_reference: Dict[str, Any],
        vulnerability_reference: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        scored: List[Dict[str, Any]] = []
        detection_index = {
            entry["question_number"]: entry for entry in detection_reference.get("questions", [])
        }
        vulnerability_index: Dict[str, Dict[str, Any]] = {}
        if vulnerability_reference:
            for entry in vulnerability_reference.get("questions", []):
                vulnerability_index[entry["question_number"]] = entry

        for entry in sorted(questions, key=self._question_sort_key):
            question_number = entry.get("question_number")
            detection_info = detection_index.get(question_number, {})
            baseline_entry = vulnerability_index.get(question_number, {})
            detection_context = self._build_detection_context(detection_info)

            candidates = []
            for answer in entry.get("answers", []):
                candidates.append(
                    {
                        "provider": answer.get("provider"),
                        "answer_label": answer.get("answer_label"),
                        "answer_text": answer.get("answer_text") or answer.get("answer"),
                    }
                )

            scored_batch = self.scoring_service.score_batch(
                question_text=entry.get("question_text", ""),
                question_type=entry.get("question_type"),
                gold_answer=entry.get("gold_answer"),
                provider_answers=candidates,
                options=entry.get("options"),
                detection_context=detection_context,
            )
            score_lookup = {item["provider"]: item for item in scored_batch}

            per_model = []
            for answer in entry.get("answers", []):
                provider = answer.get("provider")
                scorecard = score_lookup.get(provider) or {
                    "provider": provider,
                    "score": 0.0,
                    "verdict": "missing",
                    "confidence": 0.0,
                    "rationale": "Scoring unavailable.",
                    "source": "heuristic",
                }
                detection_hit = scorecard.get("hit_detection_target")
                if detection_hit is None:
                    detection_hit = self._matches_detection(answer.get("answer_text"), detection_info)
                baseline_score = self._lookup_baseline_score(baseline_entry, provider)
                per_model.append(
                    {
                        **answer,
                        "scorecard": scorecard,
                        "matches_detection_target": detection_hit,
                        "baseline_score": baseline_score,
                        "delta_from_baseline": (
                            scorecard.get("score", 0.0) - baseline_score if baseline_score is not None else None
                        ),
                        "scoring_source": scorecard.get("source"),
                    }
                )
            scored.append(
                {
                    **entry,
                    "answers": per_model,
                    "detection_target": detection_info.get("target_answer"),
                }
            )
        return scored

    def _matches_detection(self, answer: str | None, detection_info: Dict[str, Any]) -> bool | None:
        if not answer or not detection_info:
            return None
        labels = detection_info.get("target_answer", {}).get("labels") or []
        normalized_answer = self._normalize_label(answer)
        return normalized_answer in {self._normalize_label(label) for label in labels if label}

    @staticmethod
    def _build_detection_context(detection_info: Dict[str, Any]) -> Dict[str, Any] | None:
        if not detection_info:
            return None
        target = detection_info.get("target_answer") or {}
        return {
            "risk_level": detection_info.get("risk_level"),
            "target_labels": target.get("labels") or [],
            "target_texts": target.get("texts") or [],
            "raw_replacements": target.get("raw_replacements") or [],
        }

    @staticmethod
    def _question_sort_key(entry: Dict[str, Any]) -> tuple[int, int]:
        number = entry.get("question_number")
        try:
            primary = int(number)
        except (TypeError, ValueError):
            primary = 10**9
        secondary = entry.get("question_id") or 0
        return (primary, secondary)

    def _normalize_label(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        if not text:
            return None
        if text.endswith("."):
            text = text[:-1]
        return text

    def _lookup_baseline_score(self, baseline_entry: Dict[str, Any], provider: str | None) -> float | None:
        if not baseline_entry or not provider:
            return None
        for answer in baseline_entry.get("answers", []):
            if answer.get("provider") == provider:
                scorecard = answer.get("scorecard") or {}
                return float(scorecard.get("score", 0.0))
        return None

    def _build_summary(
        self,
        questions: List[Dict[str, Any]],
        baseline_reference: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        provider_totals: Dict[str, Dict[str, float]] = {}
        fooled_totals: Dict[str, int] = {}
        for entry in questions:
            for answer in entry.get("answers", []):
                provider = answer.get("provider") or "unknown"
                provider_totals.setdefault(provider, {"score_sum": 0.0, "count": 0, "delta_sum": 0.0, "delta_count": 0})
                provider_totals[provider]["score_sum"] += float(answer.get("scorecard", {}).get("score", 0.0))
                provider_totals[provider]["count"] += 1
                delta = answer.get("delta_from_baseline")
                if delta is not None:
                    provider_totals[provider]["delta_sum"] += delta
                    provider_totals[provider]["delta_count"] += 1
                if answer.get("matches_detection_target"):
                    fooled_totals[provider] = fooled_totals.get(provider, 0) + 1

        provider_summary = []
        for provider, totals in provider_totals.items():
            avg_score = (totals["score_sum"] / totals["count"]) if totals["count"] else 0.0
            avg_delta = (
                totals["delta_sum"] / totals["delta_count"]
                if totals["delta_count"] > 0
                else (None if not baseline_reference else 0.0)
            )
            provider_summary.append(
                {
                    "provider": provider,
                    "average_score": avg_score,
                    "average_delta_from_baseline": avg_delta,
                    "questions_evaluated": totals["count"],
                    "fooled_count": fooled_totals.get(provider, 0),
                }
            )
        provider_summary.sort(key=lambda item: item["provider"])
        return {
            "total_questions": len(questions),
            "providers": provider_summary,
            "baseline_available": bool(baseline_reference),
        }

    def _load_detection_reference(self, run_id: str, structured: Dict[str, Any]) -> Dict[str, Any]:
        candidates: List[str] = []
        reports_section = structured.get("reports", {})
        detection_meta = reports_section.get("detection") or {}
        artifact = detection_meta.get("artifact")
        if artifact:
            candidates.append(artifact)
        manipulation = (structured.get("manipulation_results") or {}).get("detection_report") or {}
        if manipulation.get("relative_path"):
            candidates.append(manipulation["relative_path"])
        if manipulation.get("file_path"):
            candidates.append(manipulation["file_path"])
        for candidate in candidates:
            try:
                path = resolve_run_relative_path(run_id, candidate)
                if path.exists():
                    return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
        raise ValueError("Detection report artifact not found. Generate a detection report first.")

    def _load_vulnerability_reference(self, run_id: str, structured: Dict[str, Any]) -> Dict[str, Any] | None:
        reports = structured.get("reports", {})
        vuln = reports.get("vulnerability")
        if not vuln or not vuln.get("artifact"):
            return None
        path = resolve_run_relative_path(run_id, vuln["artifact"])
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def _update_structured_data(self, run_id: str, payload: Dict[str, Any], relative_path: str) -> None:
        structured = self.structured_manager.load(run_id) or {}
        reports = structured.setdefault("reports", {})
        evaluation_bucket = reports.setdefault("evaluation", {})
        evaluation_bucket[payload["method"]] = {
            "generated_at": payload["generated_at"],
            "summary": payload["summary"],
            "artifact": relative_path,
            "method": payload["method"],
        }
        self.structured_manager.save(run_id, structured)

