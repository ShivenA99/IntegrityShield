from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .code_glyph_mapper import project_entities_to_blocks
from .layout_renderer import render_pages


def write_from_structured(structured: Dict[str, Any], output_path: Path) -> Path:
	projected = project_entities_to_blocks(structured)
	return render_pages(projected, output_path) 