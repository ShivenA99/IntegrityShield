from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from .base_ai_client import BaseAIClient, AIExtractionResult
from ...utils.logging import get_logger

try:
    # Prefer official mistralai SDK
    from mistralai import Mistral  # type: ignore
except ImportError:
    try:
        # Some environments expose client as `mistral`
        from mistral import Mistral  # type: ignore
    except Exception:
        Mistral = None  # type: ignore


class MistralOCRClient(BaseAIClient):
    """Mistral OCR client for direct PDF question extraction."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__(api_key or os.getenv("MISTRAL_API_KEY"))
        self.model = model or os.getenv("MISTRAL_MODEL", "pixtral-12b-2409")
        self.timeout_s = int(os.getenv("OCR_TIMEOUT_S", "120"))
        self.logger = get_logger(__name__)

    def is_configured(self) -> bool:
        return bool(self.api_key and Mistral)

    def extract_questions_from_pdf(self, pdf_path: Path, run_id: str) -> AIExtractionResult:
        """Extract questions directly from PDF using Mistral document OCR."""
        start_time = time.perf_counter()

        if not self.is_configured():
            return AIExtractionResult(
                source="mistral_ocr",
                confidence=0.0,
                questions=[],
                error="Mistral OCR not configured - missing API key or library"
            )

        try:
            client = Mistral(api_key=self.api_key)

            # Convert PDF to base64
            b64_pdf = base64.b64encode(pdf_path.read_bytes()).decode("utf-8")
            doc_chunk = {"type": "document_url", "document_url": f"data:application/pdf;base64,{b64_pdf}"}

            # Try document OCR first
            raw_response = None
            try:
                response = client.ocr.process(
                    model="mistral-ocr-2505",
                    document=doc_chunk,
                    include_image_base64=False,
                )
                raw_response = response.model_dump() if hasattr(response, "model_dump") else response
            except Exception as e:
                self.logger.warning(f"Mistral document OCR failed, trying fallback: {e}")

                # Fallback to annotations
                try:
                    response = client.document_ai.annotate(
                        document=doc_chunk,
                        annotation_types=["bbox", "doc_annot"],
                        include_images=False,
                    )
                    raw_response = response.model_dump() if hasattr(response, "model_dump") else response
                except Exception as e2:
                    self.logger.error(f"Mistral annotations also failed: {e2}")
                    raise e2

            # Extract page-level markdown
            pages_markdown = []
            for i, page in enumerate(raw_response.get("pages", []) or []):
                markdown = (page.get("markdown") or page.get("text") or "").strip()
                if markdown:
                    pages_markdown.append({
                        "page_number": i + 1,
                        "markdown": markdown
                    })

            # Use GPT to extract questions from markdown
            questions = self._extract_questions_from_markdown(pages_markdown, run_id)

            processing_time = int((time.perf_counter() - start_time) * 1000)
            confidence = 0.85 if questions else 0.1

            # Estimate cost
            total_chars = sum(len(page["markdown"]) for page in pages_markdown)
            cost_cents = self._estimate_cost(total_chars)

            self._log_extraction("mistral_ocr", len(questions), processing_time, run_id)

            return AIExtractionResult(
                source="mistral_ocr",
                confidence=confidence,
                questions=questions,
                raw_response=raw_response,
                processing_time_ms=processing_time,
                cost_cents=cost_cents
            )

        except Exception as e:
            self.logger.error(f"Mistral OCR PDF extraction failed: {e}", run_id=run_id, error=str(e))
            return AIExtractionResult(
                source="mistral_ocr",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def extract_questions_from_page(self, page_image: bytes, page_number: int, run_id: str) -> AIExtractionResult:
        """Extract questions from a single page image using Mistral Vision."""
        start_time = time.perf_counter()

        if not self.is_configured():
            return AIExtractionResult(
                source="mistral_ocr",
                confidence=0.0,
                questions=[],
                error="Mistral OCR not configured"
            )

        try:
            client = Mistral(api_key=self.api_key)
            b64_image = base64.b64encode(page_image).decode("utf-8")

            # Create structured prompt for question extraction
            prompt = self._create_question_extraction_prompt()

            response = client.chat.complete(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image", "image_url": f"data:image/png;base64,{b64_image}"},
                        ],
                    }
                ],
            )

            content = response.choices[0].message.content if hasattr(response.choices[0], "message") else response.choices[0]["message"]["content"]
            content = content.strip() if content else ""

            processing_time = int((time.perf_counter() - start_time) * 1000)
            cost_cents = self._estimate_cost(len(prompt) + len(content))

            # Parse questions from response
            questions = self._parse_question_response(content)

            # Add page metadata
            for i, question in enumerate(questions):
                if 'positioning' not in question:
                    question['positioning'] = {
                        'page': page_number,
                        'method': 'mistral_ocr',
                        'extraction_order': i
                    }

            confidence = 0.85 if questions else 0.2

            self.logger.info(
                f"Mistral OCR extracted {len(questions)} questions from page {page_number}",
                run_id=run_id,
                page_number=page_number,
                questions_count=len(questions),
                processing_time_ms=processing_time
            )

            return AIExtractionResult(
                source="mistral_ocr",
                confidence=confidence,
                questions=questions,
                raw_response={"content": content, "model": self.model},
                processing_time_ms=processing_time,
                cost_cents=cost_cents
            )

        except Exception as e:
            self.logger.error(
                f"Mistral OCR page extraction failed: {e}",
                run_id=run_id,
                page_number=page_number,
                error=str(e)
            )
            return AIExtractionResult(
                source="mistral_ocr",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def _extract_questions_from_markdown(self, pages_markdown: List[Dict], run_id: str) -> List[Dict[str, Any]]:
        """Extract structured questions from Mistral's markdown output."""
        if not pages_markdown:
            return []

        try:
            client = Mistral(api_key=self.api_key)

            # Combine all markdown with page markers
            combined_text = ""
            for page in pages_markdown:
                combined_text += f"\n\n=== PAGE {page['page_number']} ===\n"
                combined_text += page['markdown']

            prompt = f"""Extract ALL questions from this academic assessment document and return them as JSON:

{combined_text}

Output format:
{{
  "questions": [
    {{
      "question_number": "1",
      "question_type": "mcq_single|mcq_multi|true_false|short_answer|fill_blank|matching",
      "stem_text": "The complete question text",
      "options": {{"A": "option text", "B": "option text", ...}},
      "page_number": 1,
      "confidence": 0.9,
      "metadata": {{"source": "mistral_ocr"}}
    }}
  ]
}}

Extract EVERY question visible. Return ONLY valid JSON."""

            response = client.chat.complete(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.choices[0].message.content if hasattr(response.choices[0], "message") else response.choices[0]["message"]["content"]
            return self._parse_question_response(content or "")

        except Exception as e:
            self.logger.warning(f"Failed to extract questions from markdown: {e}")
            return []

    def _create_question_extraction_prompt(self) -> str:
        """Create structured prompt for question extraction."""
        return """Analyze this page and extract ALL questions in JSON format:

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
        "complexity": "medium"
      }
    }
  ]
}

RULES:
1. Extract EVERY question on the page
2. Number questions in order
3. Identify question types correctly
4. Separate stem text from options clearly
5. Return ONLY valid JSON

If no questions: {"questions": []}"""

    def _parse_question_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse Mistral response to extract questions."""
        try:
            # Clean up response
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                # Find first newline and remove everything before it
                nl_pos = content.find("\n")
                if nl_pos != -1:
                    content = content[nl_pos + 1:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Extract JSON
            start = content.find('{')
            end = content.rfind('}')

            if start == -1 or end == -1:
                return []

            json_str = content[start:end + 1]
            parsed = json.loads(json_str)

            questions = parsed.get('questions', [])
            validated_questions = []

            for q in questions:
                if isinstance(q, dict) and q.get('question_number') and q.get('stem_text'):
                    # Ensure required fields
                    q.setdefault('question_type', 'unknown')
                    q.setdefault('options', {})
                    q.setdefault('visual_elements', [])
                    q.setdefault('confidence', 0.8)
                    q.setdefault('metadata', {'source': 'mistral_ocr'})
                    validated_questions.append(q)

            return validated_questions

        except json.JSONDecodeError as e:
            self.logger.warning(f"Mistral JSON parsing failed: {e}", content=content[:200])
            return []
        except Exception as e:
            self.logger.warning(f"Mistral question parsing failed: {e}")
            return []

    def _estimate_cost(self, char_count: int) -> float:
        """Estimate Mistral API cost in cents."""
        # Rough estimation: ~$0.001 per 1K characters
        return (char_count / 1000) * 0.1