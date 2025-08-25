from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Optional


class AttackHandler:
    """Interface for attack implementations.

    Implementations provide hooks for:
    - applying the attack to question stems
    - generating wrong answers
    - building artifacts (attacked PDF, reports)
    - evaluation
    """

    def apply_to_stem(self, stem_text: str) -> str:
        return stem_text

    def generate_wrong_answer(
        self,
        stem_text: str,
        options: Dict[str, str],
        correct_answer: Optional[str] = None,
    ) -> Tuple[str, str]:
        return "A", "Clearly aligns with how the concept is described in the question."

    def build_artifacts(
        self,
        questions: List[Dict],
        assessment_dir: Path,
        title: str,
    ) -> Tuple[Path, Path]:
        """Return (attacked_pdf_path, report_pdf_path)."""
        raise NotImplementedError

    def evaluate(
        self,
        attacked_pdf_path: Path,
        questions: List[Dict],
        reference_answers: Dict[int, str] | Dict[str, str],
    ) -> Dict:
        """Return evaluation result dict."""
        raise NotImplementedError 