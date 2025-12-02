from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict

from ..latex_font_attack_service import LatexFontAttackService
from .base_renderer import BaseRenderer


class LatexFontAttackRenderer(BaseRenderer):
    """Renderer that executes the LaTeX font attack pipeline."""

    def __init__(self) -> None:
        super().__init__()
        self.attack_service = LatexFontAttackService()

    def render(
        self,
        run_id: str,
        original_pdf: Path,  # noqa: ARG002
        destination: Path,
        mapping: Dict[str, str],  # noqa: ARG002
    ) -> Dict[str, float | str | int | None]:
        result = self.attack_service.execute(run_id, force=False)
        artifacts = result.get("artifacts") or {}
        final_pdf_path = artifacts.get("final_pdf")

        destination.parent.mkdir(parents=True, exist_ok=True)
        if final_pdf_path:
            final_pdf = Path(final_pdf_path)
            if final_pdf.exists():
                shutil.copy2(final_pdf, destination)
            else:
                destination.write_bytes(b"")
        else:
            destination.write_bytes(b"")

        compile_summary = result.get("compile_summary") or {}
        return {
            "file_size_bytes": destination.stat().st_size if destination.exists() else 0,
            "effectiveness_score": None,
            "fonts_generated": sum(
                len(entry.get("fonts") or []) for entry in result.get("attacks") or []
            ),
            "compile_success": bool(compile_summary.get("success")),
        }
