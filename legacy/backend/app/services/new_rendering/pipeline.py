from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from .pdf_writer import write_from_structured

logger = logging.getLogger(__name__)


def render_from_structured(structured_json_path: Path, output_path: Path, *, mode: str = "vector") -> Path:
	logger.info("[NEW_RENDER] render_from_structured mode=%s structured=%s", mode, structured_json_path)
	with open(structured_json_path, "r", encoding="utf-8") as f:
		structured = json.load(f)
	try:
		return write_from_structured(structured, output_path)
	except Exception as e:
		logger.error("[NEW_RENDER] Full repaint failed: %s", e)
		raise 