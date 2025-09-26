from __future__ import annotations

import json
import os
import time
from typing import Dict, Any, Optional, List

from .base_ai_client import BaseAIClient, AIExtractionResult
from ...utils.logging import get_logger

try:
    import openai
except ImportError:
    openai = None


class GPT5FusionClient(BaseAIClient):
    """GPT-5 client for intelligent fusion of multiple data sources."""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key or os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o"  # Use GPT-4o as it's the most capable available
        self.logger = get_logger(__name__)

    def is_configured(self) -> bool:
        return bool(self.api_key and openai)

    def analyze_elements_for_questions(self, content_elements: List[Dict], run_id: str) -> AIExtractionResult:
        """Analyze PyMuPDF content elements to identify questions and generate substring-level mappings."""
        start_time = time.perf_counter()

        if not self.is_configured():
            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=0.0,
                questions=[],
                error="GPT-5 fusion not configured - missing OpenAI API key"
            )

        try:
            # Filter text elements and sort by position
            text_elements = [elem for elem in content_elements if elem.get("type") == "text"]
            text_elements.sort(key=lambda e: (e.get("bbox", [0, 0])[1], e.get("bbox", [0, 0])[0]))

            # Create analysis prompt
            prompt = self._create_question_analysis_prompt(text_elements)
            client = self._get_openai_client()

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing academic assessment documents. Your task is to identify questions, classify them, and generate strategic manipulation targets for content replacement with precise positioning."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=4000
            )

            content = response.choices[0].message.content.strip()
            processing_time = int((time.perf_counter() - start_time) * 1000)

            # Parse questions with manipulation targets
            questions = self._parse_question_analysis_response(content)
            confidence = 0.95 if questions else 0.1

            cost_cents = self._estimate_cost(len(prompt), len(content))
            self.logger.info(f"GPT-5 question analysis found {len(questions)} questions with manipulation targets", run_id=run_id)

            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=confidence,
                questions=questions,
                raw_response={"content": content, "model": self.model},
                processing_time_ms=processing_time,
                cost_cents=cost_cents
            )

        except Exception as e:
            self.logger.error(f"GPT-5 question analysis failed: {e}", run_id=run_id, error=str(e))
            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def extract_questions_from_pdf(self, pdf_path, run_id: str) -> AIExtractionResult:
        """Not implemented - GPT-5 fusion works with pre-extracted data."""
        raise NotImplementedError("GPT-5 fusion works with already extracted data from other sources")

    def extract_questions_from_page(self, page_image: bytes, page_number: int, run_id: str) -> AIExtractionResult:
        """Not implemented - GPT-5 fusion works with pre-extracted data."""
        raise NotImplementedError("GPT-5 fusion works with already extracted data from other sources")

    def fuse_extraction_results(
        self,
        pymupdf_data: Dict[str, Any],
        openai_vision_result: AIExtractionResult,
        mistral_ocr_result: AIExtractionResult,
        run_id: str
    ) -> AIExtractionResult:
        """Intelligently merge results from all three sources using GPT-5."""
        start_time = time.perf_counter()

        if not self.is_configured():
            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=0.0,
                questions=[],
                error="GPT-5 fusion not configured - missing OpenAI API key"
            )

        try:
            # Prepare fusion prompt with all source data
            fusion_prompt = self._create_fusion_prompt(
                pymupdf_data,
                openai_vision_result,
                mistral_ocr_result
            )

            client = self._get_openai_client()

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert AI system that intelligently merges question extraction results from multiple sources to produce the most accurate final output."
                    },
                    {
                        "role": "user",
                        "content": fusion_prompt
                    }
                ],
                max_tokens=6000,
                temperature=0.0
            )

            content = response.choices[0].message.content
            processing_time = int((time.perf_counter() - start_time) * 1000)

            # Parse the fused results
            fused_questions = self._parse_fusion_response(content or "")

            # Calculate confidence based on source agreement
            confidence = self._calculate_fusion_confidence(
                fused_questions,
                openai_vision_result,
                mistral_ocr_result
            )

            # Estimate cost
            cost_cents = self._estimate_cost(len(fusion_prompt), len(content or ""))

            self.logger.info(
                f"GPT-5 fusion produced {len(fused_questions)} questions from {len(openai_vision_result.questions)} + {len(mistral_ocr_result.questions)} source questions",
                run_id=run_id,
                fused_count=len(fused_questions),
                vision_count=len(openai_vision_result.questions),
                mistral_count=len(mistral_ocr_result.questions),
                confidence=confidence,
                processing_time_ms=processing_time
            )

            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=confidence,
                questions=fused_questions,
                raw_response={
                    "content": content,
                    "model": self.model,
                    "sources_used": ["pymupdf", "openai_vision", "mistral_ocr"]
                },
                processing_time_ms=processing_time,
                cost_cents=cost_cents
            )

        except Exception as e:
            self.logger.error(f"GPT-5 fusion failed: {e}", run_id=run_id, error=str(e))
            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def _create_fusion_prompt(
        self,
        pymupdf_data: Dict[str, Any],
        openai_vision_result: AIExtractionResult,
        mistral_ocr_result: AIExtractionResult
    ) -> str:
        """Create comprehensive fusion prompt with all source data."""

        prompt = """You are tasked with intelligently merging question extraction results from three different sources to produce the most accurate final question list.

# SOURCE DATA:

## PyMuPDF Raw Extraction:
```json
""" + json.dumps({
    "pages": pymupdf_data.get("document", {}).get("pages", 0),
    "content_elements": pymupdf_data.get("content_elements", [])[:50],  # Limit for prompt size
    "fonts": pymupdf_data.get("assets", {}).get("fonts", [])
}, indent=2) + """
```

## OpenAI Vision Results:
Confidence: """ + str(openai_vision_result.confidence) + """
Questions Found: """ + str(len(openai_vision_result.questions)) + """
```json
""" + json.dumps(openai_vision_result.questions, indent=2) + """
```

## Mistral OCR Results:
Confidence: """ + str(mistral_ocr_result.confidence) + """
Questions Found: """ + str(len(mistral_ocr_result.questions)) + """
```json
""" + json.dumps(mistral_ocr_result.questions, indent=2) + """
```

# FUSION INSTRUCTIONS:

1. **Question Matching**: Identify questions that appear in multiple sources
2. **Conflict Resolution**: When sources disagree, use the highest confidence source or merge intelligently
3. **Missing Questions**: Include questions found by only one source if they seem valid
4. **Data Enhancement**: Combine positioning data from PyMuPDF with understanding from AI sources
5. **Quality Control**: Validate question numbers, types, and completeness

# FUSION CRITERIA:

- **Trust Hierarchy**: OpenAI Vision > Mistral OCR > PyMuPDF (for understanding)
- **Position Trust**: PyMuPDF > AI sources (for exact positioning)
- **Completeness**: Prefer sources with complete question + options
- **Consistency**: Flag inconsistencies but include best version

# OUTPUT FORMAT:

Return a JSON object with the fused results:

```json
{
  "fusion_analysis": {
    "total_questions_found": 0,
    "source_agreements": {
      "vision_mistral": 0,
      "vision_only": 0,
      "mistral_only": 0,
      "conflicts_resolved": 0
    },
    "quality_score": 0.95
  },
  "questions": [
    {
      "question_number": "1",
      "question_type": "mcq_single",
      "stem_text": "Best version of question text",
      "options": {"A": "...", "B": "..."},
      "positioning": {
        "page": 1,
        "bbox": [x0, y0, x1, y1],
        "source": "pymupdf"
      },
      "confidence": 0.95,
      "sources_detected": ["openai_vision", "mistral_ocr"],
      "fusion_notes": "Merged from 2 sources, used Vision for text, PyMuPDF for position",
      "metadata": {
        "visual_elements": [],
        "complexity": "medium",
        "source_agreements": 2
      }
    }
  ]
}
```

Produce the most accurate, complete question extraction possible by intelligently combining all available information."""

        return prompt

    def _parse_fusion_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse GPT-5 fusion response."""
        try:
            # Clean response
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Extract JSON
            start = content.find('{')
            end = content.rfind('}')

            if start == -1 or end == -1:
                self.logger.warning("No JSON found in GPT-5 fusion response")
                return []

            json_str = content[start:end + 1]
            parsed = json.loads(json_str)

            # Extract questions and add fusion metadata
            questions = parsed.get('questions', [])
            fusion_analysis = parsed.get('fusion_analysis', {})

            validated_questions = []
            for q in questions:
                if isinstance(q, dict) and q.get('question_number') and q.get('stem_text'):
                    # Add fusion metadata
                    q.setdefault('confidence', 0.8)
                    q.setdefault('sources_detected', ['gpt5_fusion'])
                    q.setdefault('fusion_notes', 'GPT-5 intelligent fusion')
                    q.setdefault('positioning', {})
                    q.setdefault('metadata', {})

                    # Add fusion analysis to metadata
                    q['metadata']['fusion_analysis'] = fusion_analysis

                    validated_questions.append(q)

            return validated_questions

        except json.JSONDecodeError as e:
            self.logger.warning(f"GPT-5 fusion JSON parsing failed: {e}", content=content[:300])
            return []
        except Exception as e:
            self.logger.warning(f"GPT-5 fusion parsing failed: {e}")
            return []

    def _calculate_fusion_confidence(
        self,
        fused_questions: List[Dict[str, Any]],
        openai_result: AIExtractionResult,
        mistral_result: AIExtractionResult
    ) -> float:
        """Calculate confidence based on source agreement and quality."""
        if not fused_questions:
            return 0.0

        # Base confidence from source quality
        source_confidence = (openai_result.confidence + mistral_result.confidence) / 2

        # Bonus for source agreement
        agreement_bonus = 0.0
        total_sources = len(openai_result.questions) + len(mistral_result.questions)
        if total_sources > 0:
            agreement_ratio = len(fused_questions) / max(total_sources, 1)
            agreement_bonus = min(0.2, agreement_ratio * 0.1)

        # Quality bonus for complete questions
        quality_bonus = 0.0
        complete_questions = sum(
            1 for q in fused_questions
            if q.get('stem_text') and (q.get('options') or q.get('question_type') in ['short_answer', 'fill_blank'])
        )
        if fused_questions:
            quality_ratio = complete_questions / len(fused_questions)
            quality_bonus = quality_ratio * 0.1

        final_confidence = min(0.95, source_confidence + agreement_bonus + quality_bonus)
        return round(final_confidence, 2)

    def _get_openai_client(self):
        """Get OpenAI client instance."""
        if hasattr(openai, 'OpenAI'):
            return openai.OpenAI(api_key=self.api_key)
        else:
            openai.api_key = self.api_key
            return openai

    def _create_question_analysis_prompt(self, text_elements: List[Dict]) -> str:
        """Create prompt for GPT-5 to analyze elements and generate question mappings."""

        # Create element summary for analysis (limit to prevent token overflow)
        element_summary = []
        for i, elem in enumerate(text_elements[:50]):
            content = elem.get("content", "").strip()
            if len(content) > 100:
                content = content[:97] + "..."

            element_summary.append({
                "id": i,
                "content": content,
                "bbox": elem.get("bbox", [0, 0, 0, 0]),
                "font": elem.get("font", ""),
                "size": elem.get("size", 0)
            })

        return f"""
Analyze these PDF text elements (with precise positioning) to identify questions and generate strategic manipulation targets.

ELEMENTS:
{json.dumps(element_summary, indent=2)}

TASK: Generate question-level analysis with substring manipulation targets for precision overlay approach.

EXPECTED STRATEGIES:
1. **Question Numbers**: "1" → "A", "2" → "B" (number to letter confusion)
2. **Option Labels**: "a" → "b", "b" → "c", "c" → "d", "d" → "a" (rotation)
3. **Key Terms**: Strategic word replacements in stems
4. **Answer Confusion**: Subtle content changes that affect correctness

OUTPUT FORMAT (JSON only):
{{
  "questions": [
    {{
      "question_id": "q1",
      "question_number": "1",
      "question_type": "mcq_single",
      "stem_elements": [0, 1, 2],
      "option_elements": [3, 4, 5, 6],
      "manipulation_targets": [
        {{
          "target_type": "question_number",
          "element_id": 0,
          "original_substring": "Question - 1:",
          "replacement_substring": "Question - A:",
          "bbox": [72.0, 72.51, 90.0, 85.79],
          "font": "TimesNewRomanPS-BoldMT",
          "size": 12.0,
          "strategy": "number_to_letter",
          "impact": "high"
        }},
        {{
          "target_type": "option_label",
          "element_id": 3,
          "original_substring": "a.",
          "replacement_substring": "b.",
          "bbox": [90.0, 100.37, 95.0, 113.66],
          "font": "TimesNewRomanPSMT",
          "size": 12.0,
          "strategy": "option_rotation",
          "impact": "high"
        }}
      ],
      "confidence": 0.95
    }}
  ],
  "analysis": {{
    "domain": "academic",
    "question_count": 6,
    "manipulation_strategy": "strategic_confusion",
    "high_impact_targets": 12
  }}
}}

RULES:
1. Focus on HIGH-IMPACT manipulations (question numbers, option labels)
2. Use EXACT substrings from element content
3. Preserve visual layout (similar character counts)
4. Ensure precise bbox coordinates for overlay targeting
5. Create semantic confusion without obvious errors
6. Return ONLY valid JSON

Analyze and identify questions with strategic manipulation opportunities.
"""

    def _parse_question_analysis_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse GPT-5 question analysis response."""
        try:
            # Clean up response
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
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
                if isinstance(q, dict) and q.get('question_id') and q.get('manipulation_targets'):
                    # Validate manipulation targets
                    validated_targets = []
                    for target in q.get('manipulation_targets', []):
                        if (isinstance(target, dict) and
                            target.get('original_substring') and
                            target.get('replacement_substring') and
                            target.get('bbox')):

                            # Ensure required fields
                            target.setdefault('target_type', 'unknown')
                            target.setdefault('strategy', 'substitution')
                            target.setdefault('impact', 'medium')
                            target.setdefault('font', '')
                            target.setdefault('size', 12.0)

                            validated_targets.append(target)

                    if validated_targets:
                        q['manipulation_targets'] = validated_targets
                        q.setdefault('question_type', 'mcq_single')
                        q.setdefault('confidence', 0.8)
                        q.setdefault('stem_elements', [])
                        q.setdefault('option_elements', [])
                        validated_questions.append(q)

            return validated_questions

        except json.JSONDecodeError as e:
            self.logger.warning(f"GPT-5 question analysis JSON parsing failed: {e}", content=content[:200])
            return []
        except Exception as e:
            self.logger.warning(f"GPT-5 question analysis parsing failed: {e}")
            return []

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate GPT-4 API cost in cents."""
        # GPT-4 pricing: ~$0.03 per 1K prompt tokens, ~$0.06 per 1K completion tokens
        prompt_cost = (prompt_tokens / 4 / 1000) * 3.0  # Rough token estimation
        completion_cost = (completion_tokens / 4 / 1000) * 6.0
        return prompt_cost + completion_cost