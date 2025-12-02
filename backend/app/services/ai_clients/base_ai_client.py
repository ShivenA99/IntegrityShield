from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...utils.logging import get_logger


@dataclass
class AIExtractionResult:
    """Standardized result format for all AI extraction services."""
    source: str  # 'openai_vision', 'mistral_ocr', 'pymupdf'
    confidence: float  # 0.0 to 1.0
    questions: List[Dict[str, Any]]  # Extracted questions
    raw_response: Optional[Dict[str, Any]] = None  # Raw AI response for debugging
    processing_time_ms: Optional[int] = None
    cost_cents: Optional[float] = None
    error: Optional[str] = None


@dataclass
class QuestionData:
    """Standardized question format across all sources."""
    question_number: str
    question_type: str  # mcq_single, mcq_multi, true_false, short_answer, fill_blank, matching
    stem_text: str
    options: Dict[str, str]  # For MCQ types
    positioning: Dict[str, Any]  # Bounding box, page, etc.
    visual_elements: List[Dict[str, Any]]  # Images, tables, etc.
    confidence: float
    metadata: Dict[str, Any]  # Additional type-specific data


class BaseAIClient(ABC):
    """Base class for all AI clients with standardized interface."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the client is properly configured."""
        pass

    @abstractmethod
    def extract_questions_from_pdf(
        self,
        pdf_path: Path,
        run_id: str
    ) -> AIExtractionResult:
        """Extract questions from PDF and return standardized result."""
        pass

    @abstractmethod
    def extract_questions_from_page(
        self,
        page_image: bytes,
        page_number: int,
        run_id: str
    ) -> AIExtractionResult:
        """Extract questions from a single page image."""
        pass

    def _standardize_question_format(
        self,
        raw_questions: List[Dict[str, Any]]
    ) -> List[QuestionData]:
        """Convert raw AI response to standardized QuestionData format."""
        standardized = []

        for raw_q in raw_questions:
            try:
                question = QuestionData(
                    question_number=raw_q.get('question_number', 'unknown'),
                    question_type=raw_q.get('question_type', 'unknown'),
                    stem_text=raw_q.get('stem_text', ''),
                    options=raw_q.get('options', {}),
                    positioning=raw_q.get('positioning', {}),
                    visual_elements=raw_q.get('visual_elements', []),
                    confidence=raw_q.get('confidence', 0.5),
                    metadata=raw_q.get('metadata', {})
                )
                standardized.append(question)
            except Exception as e:
                self.logger.warning(f"Failed to standardize question: {e}", raw_question=raw_q)

        return standardized

    def _log_extraction(
        self,
        source: str,
        questions_count: int,
        processing_time_ms: int,
        run_id: str
    ) -> None:
        """Log extraction results for debugging."""
        self.logger.info(
            f"[{source}] Extracted {questions_count} questions in {processing_time_ms}ms",
            run_id=run_id,
            source=source,
            questions_count=questions_count,
            processing_time_ms=processing_time_ms
        )