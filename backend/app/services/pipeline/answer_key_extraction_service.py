from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz
import orjson
from flask import current_app

from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from ...utils.storage_paths import artifacts_root
from ..data_management.structured_data_manager import StructuredDataManager

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


ANSWER_KEY_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "answer_key",
        "schema": {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_number": {"type": ["string", "number"]},
                            "answer_label": {"type": ["string", "null"]},
                            "answer_text": {"type": ["string", "null"]},
                            "confidence": {"type": ["number", "null"]},
                            "rationale": {"type": ["string", "null"]},
                        },
                        "required": ["question_number"],
                        "additionalProperties": True,
                    },
                }
            },
            "required": ["answers"],
            "additionalProperties": False,
        },
    },
}


class AnswerKeyExtractionService:
    """Parses uploaded answer key PDFs and populates structured data with gold answers."""

    MAX_CHARS = 15000

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self.structured_manager = StructuredDataManager()

    def extract(self, run_id: str, answer_key_path: Path) -> Dict[str, Any]:
        artifact_dir = artifacts_root(run_id) / "answer_key_parser"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        structured = self.structured_manager.load(run_id) or {}
        answer_key_section = structured.setdefault("answer_key", {})
        answer_key_section.update(
            {
                "source_pdf": str(answer_key_path),
                "status": "pending",
                "updated_at": isoformat(utc_now()),
            }
        )
        self.structured_manager.save(run_id, structured)

        try:
            document_text = self._extract_text(answer_key_path)
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Failed to read answer key PDF for run %s: %s", run_id, exc)
            answer_key_section.update(
                {
                    "status": "error",
                    "error": f"Failed to read PDF: {exc}",
                    "updated_at": isoformat(utc_now()),
                }
            )
            self.structured_manager.save(run_id, structured)
            return answer_key_section

        (artifact_dir / "answer_key_text.txt").write_text(document_text, encoding="utf-8")

        prompt = self._build_prompt(document_text)
        responses: Dict[str, Any] = {}
        provider: str | None = None
        try:
            response_text, provider = self._invoke_openai(prompt)
            (artifact_dir / "model_response.json").write_text(response_text, encoding="utf-8")
            responses = self._parse_response(response_text)
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Answer key parsing failed for run %s: %s", run_id, exc, exc_info=True)
            answer_key_section.update(
                {
                    "status": "error",
                    "error": str(exc),
                    "updated_at": isoformat(utc_now()),
                }
            )
            self.structured_manager.save(run_id, structured)
            return answer_key_section

        coverage = {
            "parsed": len(responses),
            "updated_at": isoformat(utc_now()),
        }

        answer_key_section.update(
            {
                "status": "parsed",
                "responses": responses,
                "coverage": coverage,
                "updated_at": isoformat(utc_now()),
                "provider": provider,
            }
        )
        structured.setdefault("pipeline_metadata", {})["answer_key_available"] = True
        self.structured_manager.save(run_id, structured)
        return answer_key_section

    def _invoke_openai(self, prompt: str) -> Tuple[str, str]:
        if OpenAI is None:
            raise RuntimeError("openai Python package is not installed")

        api_key = current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not configured for answer key extraction")

        model = (
            current_app.config.get("FAIRTESTAI_ANSWER_KEY_MODEL")
            or os.getenv("FAIRTESTAI_ANSWER_KEY_MODEL")
            or current_app.config.get("OPENAI_DEFAULT_MODEL")
            or os.getenv("OPENAI_DEFAULT_MODEL")
            or "gpt-4o-mini"
        ).strip()

        client = OpenAI(api_key=api_key)
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract definitive answer keys for instructors. Respond ONLY with valid JSON "
                    "matching the exact schema provided. Do not include any explanatory text outside the JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=800,
            response_format=ANSWER_KEY_RESPONSE_SCHEMA,
        )
        message = response.choices[0].message if response.choices else None
        content = (message.content or "").strip() if message else ""
        if not content:
            raise ValueError("OpenAI returned an empty response for answer key extraction")
        return content, f"openai:{model}"

    def _extract_text(self, pdf_path: Path) -> str:
        document = fitz.open(pdf_path)
        chunks: List[str] = []
        try:
            for page_index, page in enumerate(document):
                text = page.get_text("text") or ""
                text = text.strip()
                if not text:
                    continue
                chunks.append(f"[Page {page_index + 1}]\n{text}")
        finally:
            document.close()

        combined = "\n\n".join(chunks).strip()
        if not combined:
            raise ValueError("Answer key PDF did not contain readable text")
        if len(combined) > self.MAX_CHARS:
            combined = combined[: self.MAX_CHARS] + "\n\n[truncated]"
        return combined

    def _build_prompt(self, document_text: str) -> str:
        return (
            "You are processing an exam answer key PDF that contains the authoritative answers.\n"
            "Extract every question number with its final answer. Follow these rules:\n"
            "1. Preserve question numbering exactly as shown (e.g., '1', '2a', '15').\n"
            "2. For multiple-choice questions, return `answer_label` as the option letter and `answer_text` as the option text.\n"
            "3. For true/false questions, set `answer_label` to 'True' or 'False'.\n"
            "4. For short-answer or essay questions, leave `answer_label` null and populate `answer_text` with the descriptive answer.\n"
            "5. Estimate a confidence score between 0 and 1.\n"
            "Respond using the provided JSON schema.\n\n"
            "ANSWER KEY CONTENT:\n"
            f"{document_text}"
        )

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        cleaned = response_text.strip()
        if not cleaned:
            raise ValueError("Empty response from answer key model")
        if cleaned.startswith("```"):
            cleaned = self._strip_code_fence(cleaned)
        parsed = orjson.loads(cleaned)
        if isinstance(parsed, dict) and "answers" in parsed:
            answers = parsed.get("answers") or []
        elif isinstance(parsed, list):
            answers = parsed
        else:
            raise ValueError("Model response did not include 'answers' array")

        results: Dict[str, Any] = {}
        for entry in answers:
            if not isinstance(entry, dict):
                continue
            q_number = str(entry.get("question_number") or entry.get("q_number") or "").strip()
            if not q_number:
                continue
            label = (entry.get("answer_label") or "").strip()
            if label.lower() in {"", "null"}:
                label = ""
            normalized = {
                "question_number": q_number,
                "answer_label": label or None,
                "answer_text": entry.get("answer_text"),
                "confidence": entry.get("confidence"),
                "rationale": entry.get("rationale"),
            }
            results[q_number] = normalized
        return results

    def _strip_code_fence(self, payload: str) -> str:
        fence_pattern = re.compile(r"^```(?:json)?\s*|```$", re.IGNORECASE)
        return fence_pattern.sub("", payload).strip()
