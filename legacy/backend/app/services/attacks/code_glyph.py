from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Optional

from .base import AttackHandler
from .config import get_font_mode, get_prebuilt_dir


class CodeGlyphAttack(AttackHandler):
    """POC: Code Glyph attack handler.

    - OCR/parsing remains unchanged (handled before this handler is invoked)
    - apply_to_stem: can be no-op or minimal marker injection before PoC integration
    - generate_wrong_answer: same boilerplate, different prompt intent (handled upstream)
    - build_artifacts: may call a separate PoC generator; for now, reuse existing builder contract
    - evaluate: custom evaluation strategy for code_glyph
    """

    def __init__(self, prompt_variant: str | None = None):
        self.prompt_variant = prompt_variant or "code_glyph_v1"
        self.font_mode = get_font_mode()
        self.prebuilt_dir = get_prebuilt_dir()

    def apply_to_stem(self, stem_text: str) -> str:
        # Placeholder: no-op until PoC integrated
        return stem_text

    def generate_wrong_answer(
        self,
        stem_text: str,
        options: Dict[str, str],
        correct_answer: Optional[str] = None,
    ) -> Tuple[str, str]:
        # Placeholder: use the same signature; prompts differ upstream if needed
        # Minimal: pick a heuristic different from default to mark branch
        fallback_label = next(iter(options.keys())) if options else "A"
        return fallback_label, "Selected by code_glyph heuristic placeholder."

    def build_artifacts(
        self,
        questions: List[Dict],
        assessment_dir: Path,
        title: str,
    ) -> Tuple[Path, Path]:
        # Collect per-question entities
        entities_by_qnum: Dict[str, Dict[str, str]] = {}
        for q in questions:
            qnum = str(q.get("q_number"))
            ents = q.get("code_glyph_entities") or {}
            entities_by_qnum[qnum] = ents

        # Run internalized pipeline
        from .code_glyph_runtime.pipeline import run_code_glyph_pipeline
        result = run_code_glyph_pipeline(
            title=title,
            questions=questions,
            entities_by_qnum=entities_by_qnum,
            assessment_dir=assessment_dir,
            font_mode=self.font_mode,
            prebuilt_dir=self.prebuilt_dir,
        )
        attacked_path = Path(result["attacked_pdf_path"])  # in assessment_dir/code_glyph/attacked.pdf
        # For now, no separate report PDF from builder; route will build reference report
        return attacked_path, attacked_path  # second value unused by caller

    def evaluate(
        self,
        attacked_pdf_path: Path,
        questions: List[Dict],
        reference_answers: Dict[int, str] | Dict[str, str],
    ) -> Dict:
        # Placeholder: basic structure for custom evaluation result
        return {
            "method": "code_glyph_custom",
            "parsed_answers": {},
            "ai_response": "",
            "malicious_count": 0,
        } 