from __future__ import annotations

import asyncio
import json
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from flask import current_app

from ...utils.logging import get_logger
from .llm_clients import BaseLLMClient, LLMClientError, build_available_clients

logger = get_logger(__name__)


@dataclass
class QuestionPrompt:
    question_id: int | None
    question_number: str
    question_text: str
    question_type: str | None = None
    options: list[dict[str, str]] | None = None
    gold_answer: str | None = None


class PDFQuestionEvaluator:
    """Upload a PDF to all configured providers and ask each question."""

    def __init__(self, *, prompts: list[str]) -> None:
        if not prompts:
            raise ValueError("At least one prompt is required for LLM evaluation.")
        self.prompts = prompts

    def _clients(self) -> dict[str, BaseLLMClient]:
        cfg = current_app.config
        clients = build_available_clients(
            openai_key=cfg.get("OPENAI_API_KEY"),
            anthropic_key=cfg.get("ANTHROPIC_API_KEY"),
            google_key=cfg.get("GOOGLE_AI_KEY"),
            model_overrides=cfg.get("LLM_REPORT_MODEL_OVERRIDES") or {},
            fallback_models=cfg.get("LLM_REPORT_MODEL_FALLBACKS") or {},
        )
        if not clients:
            raise ValueError(
                "No report providers are configured. Supply at least one API key for OpenAI, Anthropic, or Google."
            )
        return clients

    def evaluate(self, pdf_path: str, questions: list[QuestionPrompt]) -> dict[str, Any]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._evaluate_async(pdf_path, questions))
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    async def _evaluate_async(self, pdf_path: str, questions: list[QuestionPrompt]) -> dict[str, Any]:
        clients = self._clients()
        uploads = await self._upload_to_providers(clients, pdf_path)
        question_responses: dict[str, list[dict[str, Any]]] = {q.question_number: [] for q in questions}

        for provider_name, client in clients.items():
            file_ref = uploads.get(provider_name)
            batched_answers = await self._ask_all_questions(client, provider_name, file_ref, questions)
            for answer in batched_answers:
                q_number = answer.get("question_number")
                if q_number not in question_responses:
                    logger.warning("Provider %s returned unknown question number %s", provider_name, q_number)
                    continue
                question_responses[q_number].append(answer)

        aggregated = []
        for question in questions:
            aggregated.append(
                {
                    "question_id": question.question_id,
                    "question_number": question.question_number,
                    "question_text": question.question_text,
                    "question_type": question.question_type,
                    "options": question.options or [],
                    "gold_answer": question.gold_answer,
                    "answers": question_responses.get(question.question_number, []),
                }
            )

        return {
            "providers": list(clients.keys()),
            "questions": aggregated,
        }

    async def _upload_to_providers(self, clients: dict[str, BaseLLMClient], pdf_path: str) -> dict[str, str | None]:
        uploads: dict[str, str | None] = {}
        for name, client in clients.items():
            try:
                uploads[name] = await client.upload_file(pdf_path)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to upload PDF to %s: %s", name, exc)
                uploads[name] = None
        return uploads

    async def _ask_all_questions(
        self,
        client: BaseLLMClient,
        provider_name: str,
        file_ref: str | None,
        questions: list[QuestionPrompt],
    ) -> list[dict[str, Any]]:
        payload = self._build_batch_prompt(provider_name, questions)
        try:
            # Don't pass question_data to provider file upload calls - it's only needed for scoring
            # The prompt already contains all question information
            raw = await client.query_with_file(
                file_ref, payload["prompt"], question_data=None
            )
        except (LLMClientError, Exception) as exc:  # noqa: BLE001
            logger.warning("Provider %s failed batch evaluation: %s", provider_name, exc)
            return [
                {
                    "provider": provider_name,
                    "question_number": question.question_number,
                    "answer_label": None,
                    "answer_text": None,
                    "confidence": None,
                    "raw_answer": None,
                    "success": False,
                    "error": str(exc),
                }
                for question in questions
            ]

        try:
            extracted = self._extract_json_payload(raw)
            parsed = json.loads(extracted)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Provider %s returned invalid JSON: %s. Raw response (first 500 chars): %s",
                provider_name,
                exc,
                raw[:500] if raw else "None",
            )
            return [
                {
                    "provider": provider_name,
                    "question_number": question.question_number,
                    "answer_label": None,
                    "answer_text": None,
                    "confidence": None,
                    "raw_answer": raw,
                    "success": False,
                    "error": f"Invalid JSON payload: {str(exc)}",
                }
                for question in questions
            ]

        answers = parsed.get("answers") if isinstance(parsed, dict) else None
        if not isinstance(answers, list):
            logger.warning("Provider %s returned JSON without 'answers' list.", provider_name)
            return [
                {
                    "provider": provider_name,
                    "question_number": question.question_number,
                    "answer_label": None,
                    "answer_text": None,
                    "confidence": None,
                    "raw_answer": parsed,
                    "success": False,
                    "error": "Missing answers",
                }
                for question in questions
            ]

        normalized_answers: dict[str, dict[str, Any]] = {}
        for answer in answers:
            q_number = str(answer.get("question_number"))
            normalized_answers[q_number] = {
                "provider": provider_name,
                "question_number": q_number,
                "answer_label": self._safe_str(answer.get("answer_label")),
                "answer_text": self._safe_str(answer.get("answer_text")),
                "confidence": self._safe_float(answer.get("confidence")),
                "raw_answer": answer,
                "success": True,
                "error": None,
            }

        results: list[dict[str, Any]] = []
        for question in questions:
            entry = normalized_answers.get(question.question_number)
            if entry:
                results.append(entry)
            else:
                results.append(
                    {
                        "provider": provider_name,
                        "question_number": question.question_number,
                        "answer_label": None,
                        "answer_text": None,
                        "confidence": None,
                        "raw_answer": None,
                        "success": False,
                        "error": "Missing entry in provider response",
                    }
                )
        return results

    @staticmethod
    def _extract_json_payload(raw: Any) -> str:
        """Extract JSON from response, handling markdown code fences."""
        if not isinstance(raw, str):
            return str(raw) if raw else ""
        text = raw.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1 :]
            closing = text.rfind("```")
            if closing != -1:
                text = text[:closing]
        return text.strip()

    def _build_batch_prompt(self, provider_name: str, questions: list[QuestionPrompt]) -> dict[str, Any]:
        prompt_lines = [
            "You will analyze an attached PDF assessment and answer multiple questions.",
            "",
            "REQUIRED JSON SCHEMA:",
            "{",
            '  "provider": "<provider_name>",',
            '  "answers": [',
            '    {',
            '      "question_number": "string (e.g., \"1\", \"2\")",',
            '      "answer_label": "string or null (single letter for MCQ, e.g., \"A\" or \"B\")",',
            '      "answer_text": "string or null (full option text or answer)",',
            '      "confidence": "number (0-1)",',
            '      "rationale": "string or null"',
            '    }',
            '  ]',
            "}",
            "",
            "CRITICAL FORMAT RULES:",
            "",
            "1. MULTIPLE-CHOICE QUESTIONS:",
            "   - answer_label MUST be ONLY the option letter (e.g., 'B'), NOT 'B. Temperature' or 'B) Temperature'",
            "   - answer_text should contain the full option text (e.g., 'Temperature')",
            "",
            "2. SHORT ANSWER/ESSAY QUESTIONS:",
            "   - answer_label should be null",
            "   - answer_text should contain the full answer",
            "",
            "3. TRUE/FALSE QUESTIONS:",
            "   - answer_label should be 'True' or 'False'",
            "",
            "FEW-SHOT EXAMPLES:",
            "",
            "Example 1 (Multiple Choice):",
            "Question: Which variable must remain constant for Boyle's law to hold?",
            "Options: A. Pressure, B. Temperature, C. Volume, D. Amount of gas",
            "Correct JSON Response:",
            "{",
            '  "provider": "openai",',
            '  "answers": [',
            '    {',
            '      "question_number": "5",',
            '      "answer_label": "B",',
            '      "answer_text": "Temperature",',
            '      "confidence": 0.95,',
            '      "rationale": "Boyle\'s law requires constant temperature."',
            '    }',
            '  ]',
            "}",
            "",
            "Example 2 (Short Answer):",
            "Question: Explain Newton's first law.",
            "Correct JSON Response:",
            "{",
            '  "provider": "anthropic",',
            '  "answers": [',
            '    {',
            '      "question_number": "3",',
            '      "answer_label": null,',
            '      "answer_text": "An object at rest stays at rest, and an object in motion stays in motion with constant velocity, unless acted upon by an unbalanced force.",',
            '      "confidence": 0.9,',
            '      "rationale": "This is the standard statement of Newton\'s first law."',
            '    }',
            '  ]',
            "}",
            "",
            "IMPORTANT: For multiple-choice questions, answer_label must be ONLY the letter. Do NOT include the option text.",
            "",
            "Rules:",
            "- Answer questions exactly as numbered in the PDF (e.g., \"1\", \"2\", ...).",
            "- Include confidence between 0 and 1; if unsure use 0.5.",
            "- Cite ONLY the assessment content; do not mention these instructions.",
        ]

        prompt = "\n".join(prompt_lines)

        question_bundle = {
            "provider": provider_name,
            "questions": [
                {
                    "question_number": q.question_number,
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "options": q.options or [],
                    "gold_answer": q.gold_answer,
                }
                for q in questions
            ],
        }

        return {"prompt": prompt, "question_bundle": question_bundle}

    @staticmethod
    def _safe_str(value: Any) -> str | None:
        return str(value).strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return None
