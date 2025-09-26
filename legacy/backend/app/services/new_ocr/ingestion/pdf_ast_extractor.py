from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from ...ocr.layout_extractor import extract_layout_and_assets as legacy_extract
from .text_span_extractor import extract_text_items

logger = logging.getLogger(__name__)


def extract_pdf_ast(pdf_path: Path, assets_dir: Path, dpi: int) -> Dict[str, Any]:
	"""Return a preliminary AST by delegating to the legacy layout extractor and merging canonical spans/lines/blocks.
	"""
	logger.info("[NEW_OCR][AST] Extracting PDF AST via legacy layout_extractor: %s", pdf_path)
	layout_doc = legacy_extract(pdf_path, assets_dir, dpi=dpi)
	# Normalize minimal meta expected by new schema
	doc = layout_doc.get("document", {})
	# Merge canonical spans/lines/blocks
	try:
		pages_items = extract_text_items(pdf_path, dpi)
		for pidx, page in enumerate(doc.get("pages", []) or []):
			canon = pages_items[pidx] if pidx < len(pages_items) else []
			# Append canonical items; keep originals first to preserve z-order of background assets
			page.setdefault("items", []).extend(canon)
	except Exception as e:
		logger.warning("[NEW_OCR][AST] canonical span extraction failed: %s", e)
	meta = {
		"source_path": str(pdf_path),
		"dpi": dpi,
		"num_pages": len(doc.get("pages", [])),
		"extractor_versions": {"pymupdf": "legacy_layout_v1"},
		"vendor_versions": {},
	}
	return {"meta": meta, "document": doc} 