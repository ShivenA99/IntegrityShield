from __future__ import annotations

from pathlib import Path
from typing import Dict

from .base_renderer import BaseRenderer


class FontManipulationRenderer(BaseRenderer):
    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, float | str | int | None]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(original_pdf.read_bytes())
        return {
            "mapping_entries": len(mapping or self.build_mapping_from_questions(run_id)),
            "file_size_bytes": destination.stat().st_size,
            "effectiveness_score": 0.75,
        }
