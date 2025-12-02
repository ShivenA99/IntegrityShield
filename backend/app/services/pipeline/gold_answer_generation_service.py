from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

from flask import current_app

from ...utils.logging import get_logger
from ...utils.openai_responses import coerce_response_text
from ...utils.time import isoformat, utc_now

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore

ProgressCallback = Callable[[Dict[str, Any], Optional[Dict[str, Any]]], Union[Awaitable[None], None]]

GOLD_RESPONSE_SCHEMA = {
    "name": "goldAnswer",
    "schema": {
        "type": "object",
        "properties": {
            "gold_answer": {"type": "string"},
            "answer_label": {"type": ["string", "null"]},
            "answer_text": {"type": ["string", "null"]},
            "confidence": {"type": ["number", "null"]},
            "rationale": {"type": ["string", "null"]},
        },
        "required": ["gold_answer"],
        "additionalProperties": True,
    },
}


class GoldAnswerGenerationService:
    """Generate or normalize gold answers using GPT-5.1 Responses API."""

    MAX_CONCURRENCY = 3
    STAGGER_SECONDS = 0.2

    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self._client: Optional[AsyncOpenAI] = None
        self._model_name = current_app.config.get("FAIRTESTAI_GOLD_ANSWER_MODEL", "gpt-5.1")
        self._reasoning_effort = (
            current_app.config.get("GOLD_ANSWER_REASONING", "medium") or "medium"
        )
        self._enabled = current_app.config.get("FAIRTESTAI_ENABLE_GOLD_ANSWER_GENERATION", True)
        self._force_refresh_all: bool = current_app.config.get("GOLD_ANSWER_FORCE_REFRESH", True)
        self._force_mcq_refresh: bool = current_app.config.get("GOLD_ANSWER_FORCE_REFRESH_MCQ", True)

        api_key = current_app.config.get("OPENAI_API_KEY")
        if not self._enabled:
            self.logger.info("Gold answer generation disabled via FAIRTESTAI_ENABLE_GOLD_ANSWERS.")
            return
        if not api_key:
            self.logger.warning("Gold answer generation requires OPENAI_API_KEY.")
            self._enabled = False
            return
        if AsyncOpenAI is None:
            self.logger.warning("openai package is unavailable; cannot generate gold answers.")
            self._enabled = False
            return

        self._client = AsyncOpenAI(api_key=api_key)

    def is_configured(self) -> bool:
        return self._enabled and self._client is not None

    @staticmethod
    def is_gold_answer_satisfied(question: Dict[str, Any], *, require_label_only: bool = False) -> bool:
        value = question.get("gold_answer")
        if not isinstance(value, str):
            return False
        cleaned = value.strip()
        if not cleaned:
            return False

        q_type = str(question.get("question_type") or "").lower()
        option_map = GoldAnswerGenerationService._extract_option_map(question)
        if option_map:
            label = GoldAnswerGenerationService._normalize_label(cleaned)
            if require_label_only and cleaned != label:
                return False
            return bool(label and label in option_map)

        if GoldAnswerGenerationService._is_true_false_question(q_type, option_map):
            return cleaned.lower() in {"true", "false", "t", "f"}

        return True

    def populate_gold_answers(
        self,
        run_id: str,
        structured: Dict[str, Any],
        *,
        force: Optional[bool] = None,
        max_questions: Optional[int] = None,
        progress_callback: ProgressCallback | None = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        effective_force = self._force_refresh_all if force is None else force
        return asyncio.run(
            self.populate_gold_answers_async(
                run_id,
                structured,
                force=effective_force,
                max_questions=max_questions,
                progress_callback=progress_callback,
            )
        )

    async def populate_gold_answers_async(
        self,
        run_id: str,
        structured: Dict[str, Any],
        *,
        force: Optional[bool] = None,
        max_questions: Optional[int] = None,
        progress_callback: ProgressCallback | None = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        questions: List[Dict[str, Any]] = structured.get("questions") or []
        if not questions:
            return structured, []

        effective_force = self._force_refresh_all if force is None else force
        total_questions = len(questions)
        document = structured.get("document") or {}
        completed = 0
        updates: List[Dict[str, Any]] = []
        pending: List[Tuple[int, Dict[str, Any]]] = []

        async def emit(status: str, question_update: Optional[Dict[str, Any]] = None) -> None:
            if not progress_callback:
                return
            payload = self._build_progress_payload(status=status, total=total_questions, completed=completed)
            result = progress_callback(payload, question_update)
            if asyncio.iscoroutine(result):
                await result

        for idx, question in enumerate(questions):
            normalized_update = self._maybe_normalize_existing(question)
            if normalized_update:
                updates.append(normalized_update)

            mcq_force = self._force_mcq_refresh and self._question_has_options(question)
            if not (effective_force or mcq_force) and self.is_gold_answer_satisfied(question, require_label_only=True):
                completed += 1
                continue

            pending.append((idx, question))

        if max_questions is not None and max_questions >= 0:
            pending = pending[:max_questions]

        if not pending:
            await emit(status="completed")
            if updates:
                self._sync_ai_questions(structured)
            return structured, updates

        if not self.is_configured():
            await emit(status="partial")
            return structured, updates

        await emit(status="running")

        semaphore = asyncio.Semaphore(self.MAX_CONCURRENCY)
        tasks = [
            asyncio.create_task(self._process_question(idx, question, document, semaphore))
            for idx, question in pending
        ]

        for task in asyncio.as_completed(tasks):
            update = await task
            completed = min(total_questions, completed + 1)
            if update:
                updates.append(update)
                await emit(status="running", question_update=update)
            else:
                await emit(status="running")

        final_status = "completed" if completed >= total_questions else "partial"
        await emit(status=final_status)

        if updates:
            self._sync_ai_questions(structured)

        return structured, updates

    async def _process_question(
        self,
        position: int,
        question: Dict[str, Any],
        document: Dict[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None

        messages = self._build_prompt(question, document)
        if not messages:
            return None

        await asyncio.sleep(position * self.STAGGER_SECONDS)

        try:
            async with semaphore:
                result = await self._call_model_async(question, messages)
        except Exception as exc:  # pragma: no cover - runtime behavior
            self.logger.warning(
                "Gold answer request failed for question %s: %s",
                question.get("question_number"),
                exc,
            )
            return None

        if not result:
            return None

        return self._apply_llm_result(question, result)

    def _maybe_normalize_existing(self, question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        gold_answer = question.get("gold_answer")
        answer_metadata = question.get("answer_metadata") or {}
        answer_label = answer_metadata.get("answer_label")
        answer_text = answer_metadata.get("answer_text")

        normalized = self._normalize_gold_value(question, gold_answer, answer_label, answer_text)
        if normalized and normalized != gold_answer:
            question["gold_answer"] = normalized
            answer_metadata = question.setdefault("answer_metadata", {})
            option_map = self._extract_option_map(question)
            if option_map and normalized in option_map:
                answer_metadata["answer_label"] = normalized
                answer_metadata["answer_text"] = option_map[normalized]
            return self._build_question_update(question, source="normalized")
        return None

    def _apply_llm_result(self, question: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_gold_value(
            question,
            result.get("gold_answer"),
            result.get("answer_label"),
            result.get("answer_text"),
        )
        if not normalized:
            return None

        option_map = self._extract_option_map(question)
        answer_text = result.get("answer_text") or option_map.get(normalized)

        question["gold_answer"] = normalized
        confidence = result.get("confidence")
        if isinstance(confidence, (int, float)):
            question["gold_confidence"] = max(0.0, min(float(confidence), 1.0))
        elif confidence is None and question.get("gold_confidence") is None:
            question["gold_confidence"] = 0.85

        answer_metadata = question.setdefault("answer_metadata", {})
        answer_metadata.update(
            {
                "generator": self._model_name,
                "answer_label": normalized if option_map else result.get("answer_label"),
                "answer_text": answer_text,
                "rationale": result.get("rationale"),
            }
        )

        return self._build_question_update(question, source="llm")

    def _build_question_update(self, question: Dict[str, Any], *, source: str) -> Dict[str, Any]:
        return {
            "manipulation_id": question.get("manipulation_id"),
            "question_number": question.get("question_number") or question.get("q_number"),
            "question_id": question.get("question_id") or question.get("source_identifier"),
            "gold_answer": question.get("gold_answer"),
            "gold_confidence": question.get("gold_confidence"),
            "source": source,
        }

    def _build_prompt(self, question: Dict[str, Any], document: Dict[str, Any]) -> List[Dict[str, Any]]:
        stem = question.get("stem_text") or question.get("original_text")
        if not stem:
            return []

        question_type = (question.get("question_type") or "unknown").lower()
        options = self._extract_option_lines(question)
        metadata = question.get("metadata") or {}

        details: List[str] = [
            "Answer strictly based on the provided assessment material.",
            f"Question type: {question_type}",
        ]
        if subject := metadata.get("subject_area"):
            details.append(f"Subject: {subject}")
        if topic := metadata.get("topic"):
            details.append(f"Topic: {topic}")
        if question.get("marks"):
            details.append(f"Points: {question['marks']}")

        # Build prompt with explicit format requirements and few-shot examples
        prompt_lines = [
            "You are GPT-5.1, grading an assessment before any manipulations.",
            "",
            "REQUIRED JSON SCHEMA:",
            "{",
            '  "gold_answer": "string (required)",',
            '  "answer_label": "string or null",',
            '  "answer_text": "string or null",',
            '  "confidence": "number (0-1) or null",',
            '  "rationale": "string or null"',
            "}",
            "",
            "CRITICAL FORMAT RULES:",
            "",
            "1. MULTIPLE-CHOICE QUESTIONS:",
            "   - gold_answer MUST be ONLY the option letter (e.g., 'B'), NOT 'B. Temperature' or 'B) Temperature'",
            "   - answer_label should be the option letter (e.g., 'B')",
            "   - answer_text should be the full option text (e.g., 'Temperature')",
            "",
            "2. TRUE/FALSE QUESTIONS:",
            "   - gold_answer must be 'True' or 'False' (exact strings)",
            "",
            "3. SHORT ANSWER/ESSAY QUESTIONS:",
            "   - gold_answer should be the exact textual answer",
            "",
            "FEW-SHOT EXAMPLES:",
            "",
            "Example 1 (Multiple Choice):",
            "Question: Which variable must remain constant for Boyle's law to hold?",
            "Options:",
            "A. Pressure",
            "B. Temperature",
            "C. Volume",
            "D. Amount of gas",
            "Correct JSON Response:",
            "{",
            '  "gold_answer": "B",',
            '  "answer_label": "B",',
            '  "answer_text": "Temperature",',
            '  "confidence": 0.95,',
            '  "rationale": "Boyle\'s law states that at constant temperature, pressure and volume are inversely proportional."',
            "}",
            "",
            "Example 2 (Multiple Choice):",
            "Question: What is the SI unit of power?",
            "Options:",
            "A. Watt",
            "B. Joule",
            "C. Newton",
            "D. Pascal",
            "Correct JSON Response:",
            "{",
            '  "gold_answer": "A",',
            '  "answer_label": "A",',
            '  "answer_text": "Watt",',
            '  "confidence": 1.0,',
            '  "rationale": "Power is measured in watts (W) in the SI system."',
            "}",
            "",
            "Example 3 (True/False):",
            "Question: The unit of electrical resistance is Ohm.",
            "Correct JSON Response:",
            "{",
            '  "gold_answer": "True",',
            '  "answer_label": null,',
            '  "answer_text": null,',
            '  "confidence": 1.0,',
            '  "rationale": "Ohm is indeed the SI unit of electrical resistance."',
            "}",
            "",
            "Example 4 (Short Answer):",
            "Question: Explain Newton's first law of motion.",
            "Correct JSON Response:",
            "{",
            '  "gold_answer": "An object at rest stays at rest, and an object in motion stays in motion with constant velocity, unless acted upon by an unbalanced force.",',
            '  "answer_label": null,',
            '  "answer_text": null,',
            '  "confidence": 0.9,',
            '  "rationale": "This is the standard statement of Newton\'s first law of motion."',
            "}",
            "",
            "IMPORTANT: For multiple-choice questions, gold_answer must be ONLY the letter. Do NOT include the option text.",
            "",
            *details,
            "",
            "Question stem:",
            stem.strip(),
        ]

        if options:
            prompt_lines.append("")
            prompt_lines.append("Options:")
            prompt_lines.extend(options)

        visual_elements = question.get("visual_elements") or []
        if visual_elements:
            prompt_lines.append("")
            prompt_lines.append("Relevant visual elements:")
            for element in visual_elements:
                desc = element.get("description") or element.get("reference") or "(visual reference)"
                prompt_lines.append(f"- {desc}")

        user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": "\n".join(prompt_lines)}]
        for image_path in self._collect_image_paths(question, document)[:3]:
            image_b64 = self._encode_image(image_path)
            if image_b64:
                user_content.append(
                    {
                        "type": "input_image",
                        "image": {"data": image_b64, "format": "png"},
                    }
                )

        return [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "You extract definitive answer keys for instructors. Respond ONLY with valid JSON matching the exact schema provided. Do not include any explanatory text outside the JSON.",
                    }
                ],
            },
            {"role": "user", "content": user_content},
        ]

    async def _call_model_async(
        self,
        question: Optional[Dict[str, Any]],
        messages: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not self._client:
            return None

        try:
            metadata: Dict[str, Any] = {"task": "gold_answer_generation"}
            if question:
                if question.get("question_number") is not None:
                    metadata["question_number"] = question.get("question_number")
                if question.get("question_id") is not None:
                    metadata["question_id"] = question.get("question_id")

            # Build request parameters
            request_params = {
                "model": self._model_name,
                "input": messages,
                "max_output_tokens": 700,
                "metadata": metadata,
            }

            # Only add reasoning parameter for models that support it (o1-mini, o1-preview, gpt-4o-mini)
            if any(model_name in self._model_name.lower() for model_name in ["o1-mini", "o1-preview", "gpt-4o-mini"]):
                request_params["reasoning"] = {"effort": self._reasoning_effort}

            response = await self._client.responses.create(**request_params)
            response_id = getattr(response, "id", None)
            if question:
                q_num = question.get("question_number") or question.get("q_number") or "unknown"
                self.logger.info(
                    "Gold answer GPT-5.1 call successful for question %s (response_id: %s)",
                    q_num,
                    response_id,
                )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Gold answer responses call failed: %s", exc)
            return None

        content = coerce_response_text(response)
        if not content:
            return None

        try:
            data = self._parse_json_response(content)
        except json.JSONDecodeError as exc:
            self.logger.warning(
                "Failed to parse GPT-5.1 response: %s", exc, extra={"payload": content[:2000]}
            )
            return None

        gold_answer = data.get("gold_answer")
        if isinstance(gold_answer, list):
            gold_answer = ", ".join(str(item) for item in gold_answer if item)
        if isinstance(gold_answer, (int, float)):
            gold_answer = str(gold_answer)
        if isinstance(gold_answer, str):
            data["gold_answer"] = gold_answer.strip()

        confidence = data.get("confidence")
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError:
                confidence = None
        if isinstance(confidence, (int, float)):
            data["confidence"] = max(0.0, min(float(confidence), 1.0))
        else:
            data["confidence"] = None

        rationale = data.get("rationale")
        if isinstance(rationale, list):
            rationale = " ".join(str(item) for item in rationale if item)
        if isinstance(rationale, (int, float)):
            rationale = str(rationale)
        if isinstance(rationale, str):
            data["rationale"] = rationale.strip()

        return data

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(content)


    def _collect_image_paths(self, question: Dict[str, Any], document: Dict[str, Any]) -> List[Path]:
        paths: List[Path] = []
        for element in question.get("visual_elements") or []:
            candidate = element.get("asset_path") or element.get("image_path") or element.get("path")
            if candidate:
                path = Path(candidate)
                if path.exists():
                    paths.append(path)
        if question.get("image_path"):
            path = Path(question["image_path"])
            if path.exists():
                paths.append(path)
        asset_dir = document.get("assets_path")
        if not paths and asset_dir:
            base = Path(asset_dir)
            for candidate in base.glob("*.png"):
                paths.append(candidate)
                break
        return paths

    def _encode_image(self, path: Path) -> Optional[str]:
        try:
            return base64.b64encode(path.read_bytes()).decode("utf-8")
        except Exception:  # pragma: no cover - I/O guard
            return None

    def _extract_option_lines(self, question: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        options = question.get("options") or question.get("options_data") or []
        if isinstance(options, dict):
            for label, text in options.items():
                lines.append(f"{label}. {text}")
        elif isinstance(options, list):
            for idx, entry in enumerate(options):
                if isinstance(entry, dict):
                    label = entry.get("label") or entry.get("option") or chr(65 + idx)
                    text = entry.get("text") or entry.get("value") or entry.get("content") or ""
                    lines.append(f"{label}. {text}")
                else:
                    lines.append(f"{chr(65 + idx)}. {entry}")
        return lines

    @staticmethod
    def _extract_option_map(question: Dict[str, Any]) -> Dict[str, str]:
        options = question.get("options") or question.get("options_data")
        option_map: Dict[str, str] = {}
        if isinstance(options, dict):
            for key, value in options.items():
                label = GoldAnswerGenerationService._normalize_label(key)
                if label:
                    option_map[label] = str(value)
        elif isinstance(options, list):
            for idx, entry in enumerate(options):
                if isinstance(entry, dict):
                    label = (
                        entry.get("label")
                        or entry.get("option")
                        or entry.get("id")
                        or chr(65 + idx)
                    )
                    normalized = GoldAnswerGenerationService._normalize_label(label)
                    if normalized:
                        option_map[normalized] = str(entry.get("text") or entry.get("value") or entry.get("content") or "")
                else:
                    option_map[chr(65 + idx)] = str(entry)
        return option_map

    @staticmethod
    def _normalize_label(label: Any) -> Optional[str]:
        if label is None:
            return None
        text = str(label).strip()
        if not text:
            return None
        if len(text) == 1 and text.isalpha():
            return text.upper()
        match = re.match(r"([A-Z])[\).:\-]", text.strip(), flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
        if text.isdigit():
            return text
        if text.upper() in {"TRUE", "FALSE", "T", "F"}:
            return text.upper()
        return text.upper()

    def _normalize_gold_value(
        self,
        question: Dict[str, Any],
        gold_answer: Any,
        answer_label: Any,
        answer_text: Any,
    ) -> Optional[str]:
        option_map = self._extract_option_map(question)
        q_type = str(question.get("question_type") or "").lower()
        raw_value = gold_answer if isinstance(gold_answer, str) else None

        if option_map:
            label = (
                self._normalize_label(answer_label)
                or self._normalize_label(self._extract_label_from_string(raw_value))
                or self._infer_label_from_text(raw_value or answer_text, option_map)
            )
            if label and label in option_map:
                return label

        if self._is_true_false_question(q_type, option_map):
            tf_value = self._normalize_true_false(raw_value or answer_text)
            if tf_value:
                return tf_value

        candidate = gold_answer if isinstance(gold_answer, str) else answer_text
        if isinstance(candidate, (int, float)):
            return str(candidate)
        if isinstance(candidate, str):
            return candidate.strip() or None
        return None

    @staticmethod
    def _question_has_options(question: Dict[str, Any]) -> bool:
        options = question.get("options") or question.get("options_data")
        if isinstance(options, dict):
            return bool(options)
        if isinstance(options, list):
            return bool(options)
        return False

    @staticmethod
    def _extract_label_from_string(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        
        # Try with punctuation first (B. or B) or B:)
        match = re.match(r"^\s*([A-Z])\s*[\).\:\-]\s*", value, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
        
        # Try without punctuation but with space (B Temperature)
        match = re.match(r"^\s*([A-Z])\s+", value, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
        
        # Try just a single letter at the start (B)
        if len(value) == 1 and value.isalpha():
            return value.upper()
        
        # Try extracting first letter if it's followed by punctuation and text (B. Temperature)
        match = re.match(r"^\s*([A-Z])[\.\)\:\-]\s*.+", value, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
        
        if value.upper() in {"TRUE", "FALSE", "T", "F"}:
            return value.upper()
        
        return None

    @staticmethod
    def _infer_label_from_text(value: Any, option_map: Dict[str, str]) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = value.strip().lower()
        if not cleaned:
            return None
        for label, text in option_map.items():
            if cleaned == str(text).strip().lower():
                return label
        return None

    @staticmethod
    def _is_true_false_question(question_type: str, option_map: Dict[str, str]) -> bool:
        if "true_false" in question_type or question_type in {"true_false", "boolean"}:
            return True
        values = {text.strip().lower() for text in option_map.values()}
        return values == {"true", "false"}

    @staticmethod
    def _normalize_true_false(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = value.strip().lower()
        if cleaned in {"true", "t"}:
            return "True"
        if cleaned in {"false", "f"}:
            return "False"
        return None

    def _build_progress_payload(self, *, status: str, total: int, completed: int) -> Dict[str, Any]:
        return {
            "status": status,
            "total": total,
            "completed": min(completed, total),
            "pending": max(total - completed, 0),
            "updated_at": isoformat(utc_now()),
        }

    def _sync_ai_questions(self, structured: Dict[str, Any]) -> None:
        ai_questions = structured.get("ai_questions")
        if not ai_questions:
            return
        lookup = {
            str(entry.get("question_number") or entry.get("q_number")): entry
            for entry in structured.get("questions", [])
        }
        for entry in ai_questions:
            key = str(entry.get("question_number") or entry.get("q_number"))
            source = lookup.get(key)
            if not source:
                continue
            entry["gold_answer"] = source.get("gold_answer")
            entry["gold_confidence"] = source.get("gold_confidence")
            if source.get("answer_metadata"):
                entry["answer_metadata"] = source.get("answer_metadata")


