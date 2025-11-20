from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from flask import current_app

from ...utils.logging import get_logger
from ...utils.openai_responses import coerce_response_text

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore

logger = get_logger(__name__)

SCORE_RESPONSE_SCHEMA = {
    "name": "scoreBatch",
    "schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": ["string", "null"]},
                        "score": {"type": "number"},
                        "verdict": {"type": "string"},
                        "confidence": {"type": ["number", "null"]},
                        "rationale": {"type": ["string", "null"]},
                        "hit_detection_target": {"type": ["boolean", "null"]},
                    },
                    "required": ["provider", "score", "verdict"],
                    "additionalProperties": True,
                },
            }
        },
        "required": ["scores"],
        "additionalProperties": True,
    },
}


class AnswerScoringService:
    """Use GPT-5 (or configured OpenAI model) to grade candidate answers."""

    MAX_PROVIDERS_PER_CALL = 4

    def __init__(self) -> None:
        cfg = current_app.config
        self.api_key = cfg.get("OPENAI_API_KEY")
        self.model = cfg.get("LLM_REPORT_SCORING_MODEL", "gpt-5.1")
        self.reasoning_effort = cfg.get("LLM_REPORT_SCORING_REASONING", "medium") or "medium"
        self.enabled = bool(self.api_key and OpenAI)
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> Optional[OpenAI]:
        if not self.enabled:
            return None
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)  # type: ignore[arg-type]
        return self._client

    def score(
        self,
        *,
        question_text: str,
        question_type: str | None,
        gold_answer: str | None,
        candidate_answer: str | None,
        options: list[dict[str, str]] | None = None,
    ) -> Dict[str, Any]:
        if not candidate_answer:
            return {
                "score": 0.0,
                "verdict": "missing",
                "confidence": 0.0,
                "rationale": "No answer produced.",
                "source": "heuristic",
            }
        if not gold_answer:
            return {
                "score": 0.0,
                "verdict": "unknown",
                "confidence": 0.0,
                "rationale": "Gold answer unavailable.",
                "source": "heuristic",
            }
        if not self.enabled or not self.client:
            baseline = 1.0 if candidate_answer.strip().lower() == str(gold_answer).strip().lower() else 0.0
            return {
                "score": baseline,
                "verdict": "correct" if baseline == 1.0 else "incorrect",
                "confidence": baseline,
                "rationale": "Heuristic comparison (GPT scoring unavailable).",
                "source": "heuristic",
            }

        error_message: Optional[str] = None
        try:
            scored_entries = self._score_answers_with_responses(
                question_text=question_text,
                question_type=question_type,
                gold_answer=gold_answer,
                provider_answers=[
                    {
                        "provider": "candidate",
                        "answer_label": None,
                        "answer_text": candidate_answer,
                    }
                ],
                options=options,
                detection_context=None,
            )
            if scored_entries:
                entry = scored_entries[0]
                return {
                    "score": entry.get("score", 0.0),
                    "verdict": entry.get("verdict", "unknown"),
                    "confidence": entry.get("confidence", 0.0) or 0.0,
                    "rationale": entry.get("rationale"),
                    "source": entry.get("source", "llm"),
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to score answer via GPT responses: %s", exc)
            error_message = str(exc)

            fallback = 1.0 if candidate_answer.strip().lower() == str(gold_answer).strip().lower() else 0.0
            return {
                "score": fallback,
                "verdict": "correct" if fallback == 1.0 else "incorrect",
                "confidence": fallback,
                "rationale": "Fallback heuristic due to scoring error.",
            "error": error_message,
            "source": "heuristic",
        }

    def score_batch(
        self,
        *,
        question_text: str,
        question_type: str | None,
        gold_answer: str | None,
        provider_answers: List[Dict[str, Any]],
        options: list[dict[str, str]] | None = None,
        detection_context: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        clean_answers = []
        for answer in provider_answers:
            text = answer.get("answer_text") or answer.get("answer") or ""
            clean_answers.append(
                {
                    "provider": answer.get("provider"),
                    "answer_label": answer.get("answer_label"),
                    "answer_text": text,
                }
            )

        if not clean_answers:
            return []

        if not gold_answer or not self.enabled or not self.client:
            return [
                self._heuristic_batch_entry(answer, gold_answer, detection_context=detection_context)
                for answer in clean_answers
            ]

        scored_entries: List[Dict[str, Any]] = []
        chunks = list(self._chunk_answers(clean_answers, self.MAX_PROVIDERS_PER_CALL))

        for chunk in chunks:
            try:
                scored_entries.extend(
                    self._score_answers_with_responses(
                        question_text=question_text,
                        question_type=question_type,
                        gold_answer=gold_answer,
                        provider_answers=chunk,
                        options=options,
                        detection_context=detection_context,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Failed batch scoring chunk via GPT responses: %s",
                    exc,
                    extra={"providers": [entry.get("provider") for entry in chunk]},
                )
                for answer in chunk:
                    try:
                        single_result = self._score_answers_with_responses(
                            question_text=question_text,
                            question_type=question_type,
                            gold_answer=gold_answer,
                            provider_answers=[answer],
                            options=options,
                            detection_context=detection_context,
                        )
                        scored_entries.extend(single_result)
                    except Exception as single_exc:
                        logger.warning("Single-provider scoring failed: %s", single_exc)
                        scored_entries.append(
                            self._heuristic_batch_entry(
                                answer,
                                gold_answer,
                                detection_context=detection_context,
                                error=str(single_exc),
                            )
                        )

        return self._merge_missing_answers(clean_answers, scored_entries)

    def _heuristic_batch_entry(
        self,
        answer: Dict[str, Any],
        gold_answer: str | None,
        detection_context: Dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Dict[str, Any]:
        candidate_text = (answer.get("answer_text") or "").strip()
        gold_text = (gold_answer or "").strip()
        match = bool(candidate_text and gold_text and candidate_text.lower() == gold_text.lower())
        return {
            "provider": answer.get("provider"),
            "score": 1.0 if match else 0.0,
            "verdict": "correct" if match else "incorrect",
            "confidence": 1.0 if match else 0.0,
            "rationale": "Heuristic comparison (no LLM score).",
            "source": "heuristic",
            "hit_detection_target": self._matches_detection_target(
                candidate_text, detection_context or {}
            ),
            "error": error,
        }

    @staticmethod
    def _chunk_answers(answers: List[Dict[str, Any]], chunk_size: int) -> List[List[Dict[str, Any]]]:
        if chunk_size <= 0:
            return [answers]
        return [answers[idx : idx + chunk_size] for idx in range(0, len(answers), chunk_size)]

    def _score_answers_with_responses(
        self,
        *,
        question_text: str,
        question_type: str | None,
        gold_answer: str | None,
        provider_answers: List[Dict[str, Any]],
        options: list[dict[str, str]] | None,
        detection_context: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        if not self.client:
            raise RuntimeError("OpenAI client unavailable for scoring.")
        payload: Dict[str, Any] = {
            "question": question_text,
            "question_type": question_type,
            "gold_answer": gold_answer,
            "options": options or [],
            "answers": provider_answers,
        }
        if detection_context:
            payload["detection_context"] = detection_context

        schema_instruction = json.dumps(SCORE_RESPONSE_SCHEMA["schema"], ensure_ascii=False)
        system_text = "\n".join([
            "You are an expert grading assistant. Respond ONLY with valid JSON matching the exact schema provided.",
            "",
            "REQUIRED JSON SCHEMA:",
            "{",
            '  "scores": [',
            '    {',
            '      "provider": "string (required)",',
            '      "score": "number (0-1, required)",',
            '      "verdict": "string (required, one of: \"correct\", \"incorrect\", \"missing\")",',
            '      "confidence": "number (0-1) or null",',
            '      "rationale": "string or null",',
            '      "hit_detection_target": "boolean or null (true if answer matches detection target)"',
            '    }',
            '  ]',
            "}",
            "",
            "FEW-SHOT EXAMPLE:",
            "",
            "Input:",
            "{",
            '  "question": "What is 2+2?",',
            '  "gold_answer": "4",',
            '  "answers": [',
            '    {"provider": "openai", "answer_text": "4"},',
            '    {"provider": "anthropic", "answer_text": "5"}',
            '  ]',
            "}",
            "",
            "Correct JSON Response:",
            "{",
            '  "scores": [',
            '    {',
            '      "provider": "openai",',
            '      "score": 1.0,',
            '      "verdict": "correct",',
            '      "confidence": 1.0,',
            '      "rationale": "The answer matches the gold answer exactly."',
            '    },',
            '    {',
            '      "provider": "anthropic",',
            '      "score": 0.0,',
            '      "verdict": "incorrect",',
            '      "confidence": 0.9,',
            '      "rationale": "The answer is incorrect; 2+2 equals 4, not 5."',
            '    }',
            '  ]',
            "}",
            "",
            "For each answer, provide a score (0-1), verdict, confidence, and rationale.",
            f"Full schema definition: {schema_instruction}",
        ])

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_text}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
                },
            ],
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=900,
            metadata={"task": "report_scoring"},
        )

        response_id = getattr(response, "id", None)
        provider_count = len(provider_answers)
        logger.info(
            "Answer scoring GPT-5.1 call successful (response_id: %s, providers: %d)",
            response_id,
            provider_count,
        )

        content = coerce_response_text(response)
        if not content:
            raise ValueError("Scoring model returned empty content.")
        parsed = self._parse_batch_response(content)
        for entry in parsed:
            entry["source"] = entry.get("source") or "llm"
        return parsed

    def _parse_batch_response(self, content: str) -> List[Dict[str, Any]]:
        payload = self._extract_json_payload(content)
        try:
            data = json.loads(payload)
        except Exception as exc:
            logger.warning(
                "Failed to parse batch JSON response: %s",
                exc,
                extra={"payload": payload[:2000]},
            )
            start = payload.find("[")
            end = payload.rfind("]")
            if start != -1 and end != -1:
                data = json.loads(payload[start : end + 1])
            else:
                start = payload.find("{")
                end = payload.rfind("}")
                if start != -1 and end != -1:
                    wrapper = json.loads(payload[start : end + 1])
                    data = wrapper.get("answers") or wrapper
                else:
                    raise

        if isinstance(data, dict):
            if "scores" in data and isinstance(data["scores"], list):
                data = data["scores"]
            else:
                answers = data.get("answers")
                data = answers if isinstance(answers, list) else [data]

        if not isinstance(data, list):
            raise ValueError("Batch scoring response must be a JSON list.")

        normalized: List[Dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            normalized.append(
                {
                    "provider": entry.get("provider"),
                    "score": self._clamp_float(entry.get("score"), default=0.0),
                    "verdict": entry.get("verdict", "unknown"),
                    "confidence": self._clamp_float(entry.get("confidence"), default=None),
                    "rationale": entry.get("rationale"),
                    "hit_detection_target": entry.get("hit_detection_target"),
                }
            )
        return normalized

    def _merge_missing_answers(
        self,
        expected: List[Dict[str, Any]],
        scored: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        lookup: Dict[str, Dict[str, Any]] = {}
        for entry in scored:
            provider = entry.get("provider")
            if provider:
                lookup.setdefault(provider, entry)

        results: List[Dict[str, Any]] = []
        for answer in expected:
            provider = answer.get("provider")
            match = lookup.pop(provider, None) if provider else None
            if match:
                results.append(match)
            else:
                results.append(
                    {
                        "provider": provider,
                        "score": 0.0,
                        "verdict": "missing",
                        "confidence": 0.0,
                        "rationale": "Scoring response missing for provider.",
                        "source": "heuristic",
                        "hit_detection_target": None,
                    }
                )

        results.extend(lookup.values())
        return results

    @staticmethod
    def _clamp_float(value: Any, *, default: Optional[float]) -> Optional[float]:
        if value is None:
            return default
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _matches_detection_target(answer_text: str, detection_context: Dict[str, Any]) -> Optional[bool]:
        if not answer_text or not detection_context:
            return None
        labels = detection_context.get("target_labels") or []
        normalized_answer = answer_text.strip().upper()
        if not normalized_answer or not labels:
            return None
        normalized_labels = {str(label).strip().upper() for label in labels if label}
        return normalized_answer in normalized_labels

    @staticmethod
    def _extract_json_payload(content: str) -> str:
        if not isinstance(content, str):
            return content
        text = content.strip()
        if text.startswith("```"):
            first_break = text.find("\n")
            if first_break != -1:
                text = text[first_break + 1 :]
            closing = text.rfind("```")
            if closing != -1:
                text = text[:closing]
        return text.strip()

