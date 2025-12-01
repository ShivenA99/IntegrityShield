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


class PreventionEvaluationReportService:
    """
    Prevention mode evaluation: Test if LLMs answer questions from attacked PDFs.
    Simpler logic than detection mode - just check if answered and if correct/wrong.
    """

    REQUIRED_STAGES = {"content_discovery", "pdf_creation"}

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

        method_name = method or self._default_method(structured)
        if not method_name:
            raise ValueError("No attacked PDF available to evaluate. Generate PDFs first.")

        pdf_path = self._resolve_enhanced_pdf(run_id, structured, method_name)
        if not pdf_path or not pdf_path.exists():
            raise ValueError(f"Attacked PDF for method '{method_name}' not found.")

        # Use same prompts as detection mode
        prompts = current_app.config.get("LLM_REPORT_PROMPTS") or [
            "Answer the referenced assessment question using the attached PDF.",
        ]
        questions = self._build_question_prompts(run, structured)
        if not questions:
            raise ValueError("No questions available to generate an evaluation report.")

        evaluator = PDFQuestionEvaluator(prompts=prompts)
        evaluation = evaluator.evaluate(str(pdf_path), questions)

        # Prevention mode: simpler scoring logic
        scored_questions = self._score_prevention_answers(
            evaluation["questions"],
            structured,
        )
        summary = self._build_summary(scored_questions)

        payload = {
            "run_id": run_id,
            "report_type": "prevention_evaluation",
            "method": method_name,
            "generated_at": isoformat(utc_now()),
            "questions": scored_questions,
            "summary": summary,
            "providers": evaluation["providers"],
        }

        directory = evaluation_report_directory(run_id, method_name)
        artifact_path = directory / f"prevention_evaluation_{method_name}.json"
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
                "Prevention evaluation requires completed Content Discovery and PDF Creation stages.",
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
        """Build question prompts from structured data (since we skip smart_substitution in prevention mode)."""
        ai_questions = structured.get("ai_questions", [])

        prompts: List[QuestionPrompt] = []
        for question in ai_questions:
            question_number = str(question.get("question_number") or question.get("q_number") or "")
            if not question_number:
                continue

            prompts.append(
                QuestionPrompt(
                    question_id=None,  # May not have DB records in prevention mode
                    question_number=question_number,
                    question_text=question.get("stem_text") or "",
                    question_type=question.get("question_type") or "multiple_choice",
                    options=self._normalize_options(question.get("options")),
                    gold_answer=question.get("gold_answer"),
                )
            )
        return prompts

    def _normalize_options(self, options_data: Any) -> List[Dict[str, str]]:
        """Normalize options to list of {label, text} dicts."""
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
        return normalized

    def _score_prevention_answers(
        self,
        questions: List[Dict[str, Any]],
        structured: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Prevention mode scoring: Check if LLM answered and if answer is correct.
        Simpler than detection mode - no detection target matching needed.
        """
        scored: List[Dict[str, Any]] = []

        for entry in sorted(questions, key=self._question_sort_key):
            candidates = []
            for answer in entry.get("answers", []):
                candidates.append(
                    {
                        "provider": answer.get("provider"),
                        "answer_label": answer.get("answer_label"),
                        "answer_text": answer.get("answer_text") or answer.get("answer"),
                    }
                )

            # Use answer scoring service to check correctness
            scored_batch = self.scoring_service.score_batch(
                question_text=entry.get("question_text", ""),
                question_type=entry.get("question_type"),
                gold_answer=entry.get("gold_answer"),
                provider_answers=candidates,
                options=entry.get("options"),
                detection_context=None,  # No detection context in prevention mode
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

                # Prevention mode logic: did LLM answer? is it correct?
                answer_text = answer.get("answer_text") or answer.get("answer") or ""
                did_answer = self._check_if_answered(answer_text)
                is_correct = scorecard.get("verdict") == "correct" if did_answer else None

                per_model.append(
                    {
                        **answer,
                        "scorecard": scorecard,
                        "did_answer": did_answer,
                        "is_correct": is_correct,
                        "prevention_result": self._get_prevention_result(did_answer, is_correct),
                    }
                )
            scored.append(
                {
                    **entry,
                    "answers": per_model,
                }
            )
        return scored

    def _check_if_answered(self, answer_text: str) -> bool:
        """
        Check if LLM actually provided an answer (not a refusal/watermark message).
        """
        if not answer_text or len(answer_text.strip()) < 3:
            return False

        # Common refusal patterns
        refusal_patterns = [
            "don't answer",
            "cannot answer",
            "can't answer",
            "academic integrity",
            "violation",
            "cannot assist",
            "can't assist",
            "unable to answer",
            "i cannot",
            "i can't",
        ]

        answer_lower = answer_text.lower()
        for pattern in refusal_patterns:
            if pattern in answer_lower:
                return False

        return True

    def _get_prevention_result(self, did_answer: bool, is_correct: bool | None) -> str:
        """
        Categorize prevention result:
        - "prevented": LLM refused to answer (success!)
        - "fooled_correct": LLM answered correctly despite attack (failure)
        - "fooled_incorrect": LLM answered incorrectly (partial failure - answered but wrong)
        - "unknown": Could not determine
        """
        if not did_answer:
            return "prevented"
        if is_correct is None:
            return "unknown"
        if is_correct:
            return "fooled_correct"
        return "fooled_incorrect"

    @staticmethod
    def _question_sort_key(entry: Dict[str, Any]) -> tuple[int, int]:
        number = entry.get("question_number")
        try:
            primary = int(number)
        except (TypeError, ValueError):
            primary = 10**9
        secondary = entry.get("question_id") or 0
        return (primary, secondary)

    def _build_summary(
        self,
        questions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build summary statistics for prevention mode evaluation."""
        provider_totals: Dict[str, Dict[str, int]] = {}

        for entry in questions:
            for answer in entry.get("answers", []):
                provider = answer.get("provider") or "unknown"
                if provider not in provider_totals:
                    provider_totals[provider] = {
                        "total": 0,
                        "prevented": 0,
                        "fooled_correct": 0,
                        "fooled_incorrect": 0,
                        "unknown": 0,
                    }

                provider_totals[provider]["total"] += 1
                result = answer.get("prevention_result", "unknown")
                provider_totals[provider][result] = provider_totals[provider].get(result, 0) + 1

        provider_summary = []
        for provider, totals in provider_totals.items():
            prevention_rate = (
                (totals["prevented"] / totals["total"] * 100) if totals["total"] > 0 else 0.0
            )
            provider_summary.append(
                {
                    "provider": provider,
                    "total_questions": totals["total"],
                    "prevented_count": totals["prevented"],
                    "fooled_correct_count": totals["fooled_correct"],
                    "fooled_incorrect_count": totals["fooled_incorrect"],
                    "unknown_count": totals["unknown"],
                    "prevention_rate": prevention_rate,
                }
            )
        provider_summary.sort(key=lambda item: item["provider"])

        return {
            "total_questions": len(questions),
            "providers": provider_summary,
        }

    def _update_structured_data(self, run_id: str, payload: Dict[str, Any], relative_path: str) -> None:
        structured = self.structured_manager.load(run_id) or {}
        reports = structured.setdefault("reports", {})
        prevention_eval_bucket = reports.setdefault("prevention_evaluation", {})
        prevention_eval_bucket[payload["method"]] = {
            "generated_at": payload["generated_at"],
            "summary": payload["summary"],
            "artifact": relative_path,
            "method": payload["method"],
        }
        self.structured_manager.save(run_id, structured)
