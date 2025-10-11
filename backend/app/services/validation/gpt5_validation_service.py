from __future__ import annotations

import json
import os
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from ..ai_clients.base_ai_client import BaseAIClient
from ...utils.logging import get_logger

try:
    import openai
except ImportError:
    openai = None


@dataclass
class ValidationResult:
    """Result of GPT-5 answer validation."""
    is_valid: bool
    confidence: float
    deviation_score: float
    reasoning: str
    semantic_similarity: float
    factual_accuracy: bool
    question_type_specific_notes: str
    gold_answer: str
    test_answer: str
    model_used: str
    target_matched: Optional[bool] = None
    signal_detected: Optional[bool] = None
    diagnostics: Optional[Dict[str, Any]] = None


class GPT5ValidationService:
    """
    Advanced validation service that uses GPT-5 to intelligently compare answers
    with question-type aware analysis and confidence scoring.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = "gpt-4o"  # Use GPT-4o as the most capable available
        self.logger = get_logger(__name__)

        # Confidence thresholds for validation
        self.validation_thresholds = {
            "mcq_single": 0.8,      # High threshold for MCQ - clear right/wrong
            "mcq_multi": 0.75,      # Slightly lower for multi-select
            "true_false": 0.85,     # Very high for T/F - binary choice
            "short_answer": 0.6,    # Lower for subjective answers
            "fill_blank": 0.7,      # Medium for fill-in-the-blank
            "match": 0.75,          # Medium-high for matching
            "long_answer": 0.5,     # Lowest for essay-type questions
            "comprehension_qa": 0.65, # Medium for reading comprehension
            "default": 0.7          # Default threshold
        }

    def is_configured(self) -> bool:
        """Check if the service is properly configured."""
        return bool(self.api_key and openai)

    def validate_answer_deviation(
        self,
        question_text: str,
        question_type: str,
        gold_answer: str,
        test_answer: str,
        options_data: Optional[Dict[str, str]] = None,
        target_option: Optional[str] = None,
        target_option_text: Optional[str] = None,
        signal_metadata: Optional[Dict[str, str]] = None,
        run_id: Optional[str] = None,
    ) -> ValidationResult:
        """
        Use GPT-5 to intelligently validate if test answer deviates enough from gold answer
        to indicate successful manipulation.
        """
        start_time = time.perf_counter()

        if not self.is_configured():
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                deviation_score=0.0,
                reasoning="GPT-5 validation not configured - missing OpenAI API key",
                semantic_similarity=0.0,
                factual_accuracy=False,
                question_type_specific_notes="Configuration error",
                gold_answer=gold_answer,
                test_answer=test_answer,
                model_used="none"
            )

        try:
            # Create specialized validation prompt based on question type
            prompt = self._create_validation_prompt(
                question_text=question_text,
                question_type=question_type,
                gold_answer=gold_answer,
                test_answer=test_answer,
                options_data=options_data,
                target_option=target_option,
                target_option_text=target_option_text,
                signal_metadata=signal_metadata,
            )

            client = self._get_openai_client()

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational assessment validator. Your task is to determine if student answers indicate successful question manipulation by comparing gold standard answers with test responses using sophisticated analysis."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent analysis
                max_tokens=1500
            )

            content = response.choices[0].message.content.strip()
            processing_time = int((time.perf_counter() - start_time) * 1000)

            # Parse the validation response
            validation_result = self._parse_validation_response(
                content, question_type, gold_answer, test_answer
            )

            # Log the validation result
            self.logger.info(
                "GPT-5 validation completed",
                run_id=run_id,
                question_type=question_type,
                confidence=validation_result.confidence,
                deviation_score=validation_result.deviation_score,
                is_valid=validation_result.is_valid,
                target_option=target_option,
                signal_phrase=(signal_metadata or {}).get("signal_phrase") if signal_metadata else None,
                processing_time_ms=processing_time,
            )

            return validation_result

        except Exception as e:
            self.logger.error(f"GPT-5 validation failed: {e}", run_id=run_id, error=str(e))
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                deviation_score=0.0,
                reasoning=f"Validation error: {str(e)}",
                semantic_similarity=0.0,
                factual_accuracy=False,
                question_type_specific_notes="Processing error",
                gold_answer=gold_answer,
                test_answer=test_answer,
                model_used=self.model
            )

    def _create_validation_prompt(
        self,
        question_text: str,
        question_type: str,
        gold_answer: str,
        test_answer: str,
        options_data: Optional[Dict[str, str]] = None,
        target_option: Optional[str] = None,
        target_option_text: Optional[str] = None,
        signal_metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Create a specialized validation prompt based on question type."""

        # Base prompt structure
        prompt = f"""
VALIDATION TASK: Analyze if a test answer indicates successful question manipulation.

QUESTION TYPE: {question_type}
QUESTION: {question_text}

GOLD ANSWER (Original): {gold_answer}
TEST ANSWER (After Manipulation): {test_answer}
"""

        # Add options if available
        if options_data:
            prompt += "\nQUESTION OPTIONS:\n"
            for key, value in options_data.items():
                prompt += f"{key}. {value}\n"

        if target_option:
            target_summary = target_option_text or "unknown target text"
            prompt += (
                "\nEXPECTED TARGET OUTCOME:\n"
                f"- Manipulated answer should now be option {target_option} ({target_summary}).\n"
                "- Evaluate whether the test answer aligns with this target rather than the gold answer.\n"
            )

        if signal_metadata:
            prompt += "\nSIGNAL METADATA (for diagnostic analysis):\n"
            prompt += json.dumps(signal_metadata, indent=2)
            prompt += (
                "\nUse the signal phrase/notes alongside the gold answer when scoring deviation and confidence.\n"
            )

        # Add question-type specific analysis instructions
        type_instructions = self._get_type_specific_instructions(question_type)
        prompt += f"\n{type_instructions}\n"

        # Add general analysis framework
        prompt += """
ANALYSIS FRAMEWORK:

1. **Semantic Similarity Analysis**:
   - Are the answers conceptually the same?
   - Do they represent the same knowledge/understanding?
   - Rate similarity: 0.0 (completely different) to 1.0 (identical meaning)

2. **Factual Accuracy Assessment**:
   - Is the test answer factually correct for the given question?
   - Does it demonstrate proper understanding?

3. **Manipulation Detection**:
   - Does the difference suggest successful question manipulation?
   - Could the change indicate confusion from altered question elements?
   - Consider: question numbers, option labels, key terms, etc.

4. **Deviation Scoring**:
   - Calculate deviation: 0.0 (identical) to 1.0 (completely different)
   - Higher scores indicate more successful manipulation

5. **Confidence Assessment**:
   - How confident are you in this analysis?
   - Account for answer clarity, question complexity, etc.

OUTPUT FORMAT (JSON only):
{
  "analysis": {
    "semantic_similarity": 0.85,
    "factual_accuracy": false,
    "deviation_score": 0.75,
    "manipulation_detected": true,
    "confidence": 0.90
  },
  "reasoning": "Detailed explanation of the analysis and decision",
  "question_type_notes": "Specific observations for this question type",
  "validation_decision": {
    "is_valid": true,
    "threshold_met": true,
    "recommended_action": "accept_as_manipulated"
  }
}

IMPORTANT: Return ONLY valid JSON. Be thorough but precise in your analysis.
"""

        return prompt

    def _get_type_specific_instructions(self, question_type: str) -> str:
        """Get specialized analysis instructions for each question type."""

        instructions = {
            "mcq_single": """
SINGLE CHOICE MCQ ANALYSIS:
- Focus on option letter changes (A→B, B→C, etc.)
- Check if answer represents different option choice
- Consider question number confusion (1→2, etc.)
- High deviation expected for successful manipulation
- Threshold: answers must be clearly different options
""",
            "mcq_multi": """
MULTIPLE CHOICE MCQ ANALYSIS:
- Compare sets of selected options
- Analyze partial vs complete selection changes
- Consider option label rotation or confusion
- Moderate to high deviation for successful manipulation
- Threshold: significant change in option selection pattern
""",
            "true_false": """
TRUE/FALSE ANALYSIS:
- Binary comparison: True vs False
- Consider negation effects from text manipulation
- Look for subtle word changes affecting truth value
- Very high deviation expected (opposite answers)
- Threshold: answers must be opposite boolean values
""",
            "short_answer": """
SHORT ANSWER ANALYSIS:
- Compare conceptual understanding
- Allow for paraphrasing and expression differences
- Focus on factual accuracy and core concepts
- Highlight when key terms are inverted (benefit→risk, increase→decrease, etc.)
- Assume manipulation strategies favour opposites or negated claims
- Threshold: significant conceptual difference required
""",
            "fill_blank": """
FILL-IN-THE-BLANK ANALYSIS:
- Compare exact terms or acceptable synonyms
- Consider manipulation of context affecting answer choice
- Check if different terms indicate different understanding
- Moderate deviation threshold
- Threshold: different terms with different meanings
""",
            "match": """
MATCHING ANALYSIS:
- Compare matching pairs or sequences
- Look for systematic shifts in matching patterns
- Consider label or number manipulation effects
- Analyze if different matches indicate confusion
- Threshold: significant change in matching accuracy
""",
            "long_answer": """
LONG ANSWER ANALYSIS:
- Compare overall argument and key points
- Allow for different expressions of same concepts
- Focus on major factual or conceptual differences
- Consider manipulation affecting core understanding
- Lower threshold due to subjective nature
""",
            "comprehension_qa": """
READING COMPREHENSION ANALYSIS:
- Compare understanding of passage content
- Check if answers reflect different interpretations
- Consider manipulation affecting reading comprehension
- Analyze factual accuracy against source material
- Moderate threshold for interpretation differences
"""
        }

        return instructions.get(question_type, instructions.get("mcq_single", ""))

    def _parse_validation_response(
        self,
        content: str,
        question_type: str,
        gold_answer: str,
        test_answer: str
    ) -> ValidationResult:
        """Parse GPT-5 validation response into structured result."""

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
                raise ValueError("No JSON found in response")

            json_str = content[start:end + 1]
            parsed = json.loads(json_str)

            # Extract analysis data
            analysis = parsed.get('analysis', {})
            validation_decision = parsed.get('validation_decision', {})

            # Calculate validation based on confidence and threshold
            confidence = float(analysis.get('confidence', 0.5))
            deviation_score = float(analysis.get('deviation_score', 0.0))
            threshold = self.validation_thresholds.get(question_type, self.validation_thresholds['default'])

            # A mapping is considered valid (successfully manipulated) if:
            # 1. High confidence in analysis
            # 2. Significant deviation detected
            # 3. Meets question-type specific threshold
            is_valid = (
                confidence >= threshold and
                deviation_score >= 0.3 and  # Minimum deviation required
                validation_decision.get('is_valid', False)
            )

            return ValidationResult(
                is_valid=is_valid,
                confidence=confidence,
                deviation_score=deviation_score,
                reasoning=parsed.get('reasoning', 'No reasoning provided'),
                semantic_similarity=float(analysis.get('semantic_similarity', 0.0)),
                factual_accuracy=analysis.get('factual_accuracy', False),
                question_type_specific_notes=parsed.get('question_type_notes', ''),
                gold_answer=gold_answer,
                test_answer=test_answer,
                model_used=self.model
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.logger.warning(f"Failed to parse GPT-5 validation response: {e}", content=content[:200])

            # Fallback: simple string comparison with question-type awareness
            fallback_deviation = self._calculate_fallback_deviation(gold_answer, test_answer, question_type)
            fallback_confidence = 0.3  # Low confidence for fallback

            return ValidationResult(
                is_valid=fallback_deviation > 0.5,
                confidence=fallback_confidence,
                deviation_score=fallback_deviation,
                reasoning="Fallback analysis due to parsing error",
                semantic_similarity=1.0 - fallback_deviation,
                factual_accuracy=False,
                question_type_specific_notes="Parsing error - used simple comparison",
                gold_answer=gold_answer,
                test_answer=test_answer,
                model_used="fallback"
            )

    def _calculate_fallback_deviation(self, gold_answer: str, test_answer: str, question_type: str) -> float:
        """Calculate simple deviation score as fallback."""
        if not gold_answer or not test_answer:
            return 0.0

        gold_clean = gold_answer.strip().lower()
        test_clean = test_answer.strip().lower()

        if gold_clean == test_clean:
            return 0.0

        # For MCQ types, different answers = high deviation
        if question_type in ["mcq_single", "mcq_multi", "true_false"]:
            return 0.8 if gold_clean != test_clean else 0.0

        # For text-based answers, use simple character difference
        if len(gold_clean) == 0:
            return 1.0

        different_chars = sum(1 for a, b in zip(gold_clean, test_clean) if a != b)
        different_chars += abs(len(gold_clean) - len(test_clean))

        return min(1.0, different_chars / max(len(gold_clean), len(test_clean)))

    def _get_openai_client(self):
        """Get OpenAI client instance."""
        if hasattr(openai, 'OpenAI'):
            return openai.OpenAI(api_key=self.api_key)
        else:
            openai.api_key = self.api_key
            return openai

    def get_validation_threshold(self, question_type: str) -> float:
        """Get the validation threshold for a specific question type."""
        return self.validation_thresholds.get(question_type, self.validation_thresholds['default'])

    def batch_validate_mappings(
        self,
        questions_data: List[Dict[str, Any]],
        run_id: Optional[str] = None
    ) -> List[ValidationResult]:
        """Validate multiple questions in a batch for efficiency."""
        results = []

        for question_data in questions_data:
            result = self.validate_answer_deviation(
                question_text=question_data.get('question_text', ''),
                question_type=question_data.get('question_type', 'mcq_single'),
                gold_answer=question_data.get('gold_answer', ''),
                test_answer=question_data.get('test_answer', ''),
                options_data=question_data.get('options_data'),
                run_id=run_id
            )
            results.append(result)

        return results
