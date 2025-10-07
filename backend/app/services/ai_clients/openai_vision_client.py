from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

import fitz
from PIL import Image
import io

from .base_ai_client import BaseAIClient, AIExtractionResult
from ...utils.logging import get_logger

try:
    import openai
except ImportError:
    openai = None


class OpenAIVisionClient(BaseAIClient):
    """OpenAI Vision client for question extraction from PDF pages."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__(api_key or os.getenv("OPENAI_API_KEY"))
        self.model = (model or os.getenv("OPENAI_VISION_MODEL", "gpt-4o")).strip()
        self.logger = get_logger(__name__)

    def is_configured(self) -> bool:
        return bool(self.api_key and openai)

    def extract_questions_from_pdf(self, pdf_path: Path, run_id: str) -> AIExtractionResult:
        """Extract questions from entire PDF by processing each page."""
        start_time = time.perf_counter()
        all_questions = []
        total_cost = 0.0

        if not self.is_configured():
            return AIExtractionResult(
                source="openai_vision",
                confidence=0.0,
                questions=[],
                error="OpenAI Vision not configured - missing API key or library"
            )

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(doc.page_count):
                page = doc[page_num]

                # Convert page to high-quality image
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scaling for quality
                img_bytes = pix.tobytes("png")

                # Extract questions from this page
                page_result = self.extract_questions_from_page(img_bytes, page_num + 1, run_id)

                if page_result.questions:
                    # Add page info to each question
                    for question in page_result.questions:
                        question['page_number'] = page_num + 1
                        question['source_page'] = f"page_{page_num + 1}"

                    all_questions.extend(page_result.questions)

                if page_result.cost_cents:
                    total_cost += page_result.cost_cents

            doc.close()

            processing_time = int((time.perf_counter() - start_time) * 1000)
            confidence = 0.9 if all_questions else 0.0

            self._log_extraction("openai_vision", len(all_questions), processing_time, run_id)

            return AIExtractionResult(
                source="openai_vision",
                confidence=confidence,
                questions=all_questions,
                processing_time_ms=processing_time,
                cost_cents=total_cost
            )

        except Exception as e:
            self.logger.error(f"OpenAI Vision PDF extraction failed: {e}", run_id=run_id, error=str(e))
            return AIExtractionResult(
                source="openai_vision",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def extract_questions_from_page(self, page_image: bytes, page_number: int, run_id: str) -> AIExtractionResult:
        """Extract questions from a single page image using OpenAI Vision."""
        start_time = time.perf_counter()

        if not self.is_configured():
            return AIExtractionResult(
                source="openai_vision",
                confidence=0.0,
                questions=[],
                error="OpenAI Vision not configured"
            )

        try:
            # Convert to base64
            b64_image = base64.b64encode(page_image).decode('utf-8')

            # Create structured prompt for question extraction
            prompt = self._create_question_extraction_prompt()

            client = self._get_openai_client()

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
                    ]
                }
            ]

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4000,
                temperature=0.0
            )

            content = response.choices[0].message.content
            processing_time = int((time.perf_counter() - start_time) * 1000)

            # Estimate cost (rough approximation)
            cost_cents = self._estimate_cost(len(prompt), len(content or ""))

            # Parse JSON response
            questions = self._parse_question_response(content or "")

            # Add positioning metadata for each question
            for i, question in enumerate(questions):
                if 'positioning' not in question:
                    question['positioning'] = {
                        'page': page_number,
                        'method': 'openai_vision',
                        'extraction_order': i
                    }

            confidence = 0.9 if questions else 0.2

            self.logger.info(
                f"OpenAI Vision extracted {len(questions)} questions from page {page_number}",
                run_id=run_id,
                page_number=page_number,
                questions_count=len(questions),
                processing_time_ms=processing_time
            )

            return AIExtractionResult(
                source="openai_vision",
                confidence=confidence,
                questions=questions,
                raw_response={"content": content, "model": self.model},
                processing_time_ms=processing_time,
                cost_cents=cost_cents
            )

        except Exception as e:
            self.logger.error(
                f"OpenAI Vision page extraction failed: {e}",
                run_id=run_id,
                page_number=page_number,
                error=str(e)
            )
            return AIExtractionResult(
                source="openai_vision",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def locate_mapping_geometry(
        self,
        page_image: bytes,
        page_number: int,
        questions: List[Dict[str, Any]],
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request bounding boxes for specified substrings using OpenAI Vision."""
        if not self.is_configured():
            raise RuntimeError("OpenAI Vision not configured - cannot refresh geometry")

        if not questions:
            return {"geometry": [], "warnings": []}

        b64_image = base64.b64encode(page_image).decode('utf-8')
        payload = {
            "task": "Identify the bounding boxes of the specified substrings within the provided question stems.",
            "page": page_number,
            "questions": questions,
        }

        instructions = (
            "You receive a PDF page image and JSON describing question stems with substrings that must be located. "
            "Return JSON with two keys: `geometry` and `warnings`. Each `geometry` entry MUST include `question_number`, "
            "`substring`, `occurrence` (integer), `bbox` ([x0, y0, x1, y1] in the page coordinate system), and an optional "
            "`confidence` score between 0 and 1. If a substring cannot be located, add an object to `warnings` with fields "
            "`question_number`, `substring`, `occurrence`, and `reason`."
        )

        client = self._get_openai_client()

        messages = [
            {
                "role": "system",
                "content": "You are an OCR assistant that provides precise bounding boxes for substrings within assessment stems.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{instructions}\n\n# Geometry Request\n{json.dumps(payload, ensure_ascii=False)}",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                    },
                ],
            },
        ]

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                "OpenAI Vision geometry call failed",
                run_id=run_id,
                page_number=page_number,
                error=str(exc),
            )
            raise

        content = response.choices[0].message.content if response.choices else ""
        if not content:
            raise ValueError("OpenAI Vision returned empty geometry response")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:  # noqa: BLE001
            self.logger.warning(
                "OpenAI Vision geometry JSON decode failed",
                run_id=run_id,
                page_number=page_number,
                error=str(exc),
                preview=content[:2000],
            )
            raise

        if not isinstance(data, dict):
            raise ValueError("OpenAI Vision geometry response was not a JSON object")

        data.setdefault("geometry", [])
        data.setdefault("warnings", [])
        return data

    def _get_openai_client(self):
        """Get OpenAI client instance."""
        if hasattr(openai, 'OpenAI'):
            return openai.OpenAI(api_key=self.api_key)
        else:
            # Legacy SDK support
            openai.api_key = self.api_key
            return openai

    def _create_question_extraction_prompt(self) -> str:
        """Create structured prompt for question extraction."""
        return """Analyze this academic assessment page and extract ALL questions in the following JSON format:

{
  "questions": [
    {
      "question_number": "1",
      "question_type": "mcq_single|mcq_multi|true_false|short_answer|fill_blank|matching",
      "stem_text": "The complete question text without options",
      "options": {"A": "option text", "B": "option text", ...},
      "visual_elements": ["table", "diagram", "equation"],
      "confidence": 0.95,
      "metadata": {
        "has_images": false,
        "complexity": "medium",
        "subject_area": "detected subject"
      }
    }
  ]
}

QUESTION TYPE RULES:
- mcq_single: Multiple choice with one correct answer
- mcq_multi: Multiple choice with multiple correct answers
- true_false: True/False or Yes/No questions
- short_answer: Open-ended text response questions
- fill_blank: Questions with blanks to fill in
- matching: Match items from two lists

EXTRACTION RULES:
1. Extract EVERY question visible on the page
2. Number questions in order they appear
3. For MCQ: separate stem from options clearly
4. For True/False: include the statement as stem_text
5. Identify visual elements (diagrams, tables, equations)
6. Estimate confidence based on text clarity
7. Return ONLY valid JSON - no explanations

If no questions found, return: {"questions": []}"""

    def _parse_question_response(self, content: str) -> list[Dict[str, Any]]:
        """Parse OpenAI Vision response to extract questions."""
        try:
            # Clean up the response - remove markdown fences if present
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Find JSON object
            start = content.find('{')
            end = content.rfind('}')

            if start == -1 or end == -1:
                self.logger.warning("No JSON found in OpenAI Vision response")
                return []

            json_str = content[start:end + 1]
            parsed = json.loads(json_str)

            questions = parsed.get('questions', [])

            # Validate and clean up question data
            validated_questions = []
            for q in questions:
                if isinstance(q, dict) and q.get('question_number') and q.get('stem_text'):
                    # Ensure required fields exist
                    q.setdefault('question_type', 'unknown')
                    q.setdefault('options', {})
                    q.setdefault('visual_elements', [])
                    q.setdefault('confidence', 0.8)
                    q.setdefault('metadata', {})
                    validated_questions.append(q)

            return validated_questions

        except json.JSONDecodeError as e:
            self.logger.warning(f"JSON parsing failed: {e}", content=content[:200])
            return []
        except Exception as e:
            self.logger.warning(f"Question parsing failed: {e}")
            return []

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate API cost in cents (rough approximation)."""
        # GPT-4 Vision rough pricing: ~$0.03 per 1K tokens
        total_tokens = (prompt_tokens + completion_tokens) / 4  # Rough token estimation
        return (total_tokens / 1000) * 3.0  # ~3 cents per 1K tokens
