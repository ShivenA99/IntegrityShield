from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def _flags_to_style(flags: int) -> Tuple[str, bool]:
	# Heuristic: 1=bold, 2=italic (varies by backend)
	bold = bool(flags & 1)
	italic = bool(flags & 2)
	weight = "bold" if bold else "normal"
	return weight, italic


def extract_text_items(pdf_path: Path, dpi: int) -> List[List[Dict[str, Any]]]:
	"""Return per-page canonical text items: [ [items...], ... ].
	Items include text_span, text_line, text_block with child linkage.
	"""
	doc = fitz.open(str(pdf_path))
	pages: List[List[Dict[str, Any]]] = []
	try:
		for pidx in range(len(doc)):
			page = doc.load_page(pidx)
			tdict = page.get_text("dict") or {}
			items: List[Dict[str, Any]] = []
			z = 0
			for bi, block in enumerate(tdict.get("blocks", []) or []):
				if int(block.get("type", 0)) != 0:
					continue
				bb = list(block.get("bbox", (0, 0, 0, 0)))
				line_ids: List[str] = []
				for li, line in enumerate(block.get("lines", []) or []):
					lb = list(line.get("bbox", (0, 0, 0, 0)))
					span_ids: List[str] = []
					for si, span in enumerate(line.get("spans", []) or []):
						sp_id = f"p{pidx}-sp{bi}_{li}_{si}"
						flags = int(span.get("flags", 0))
						weight, italic = _flags_to_style(flags)
						color = span.get("color", 0)
						if isinstance(color, tuple):
							col = color
						else:
							# convert int color to RGB (approx); PyMuPDF stores as int sometimes
							col = (0, 0, 0)
						span_item = {
							"id": sp_id,
							"type": "text_span",
							"bbox": lb,  # span bbox not directly provided; use line bbox as conservative host
							"text": span.get("text", ""),
							"font_family": span.get("font", ""),
							"font_size": float(span.get("size", 0.0)),
							"weight": weight,
							"italic": italic,
							"color": col,
							"z": z,
						}
						items.append(span_item)
						span_ids.append(sp_id)
						z += 1
					ln_id = f"p{pidx}-ln{bi}_{li}"
					line_item = {
						"id": ln_id,
						"type": "text_line",
						"bbox": lb,
						"children": span_ids,
						"z": z,
					}
					items.append(line_item)
					line_ids.append(ln_id)
					z += 1
				blk_id = f"p{pidx}-tbk{bi}"
				block_item = {
					"id": blk_id,
					"type": "text_block",
					"bbox": bb,
					"children": line_ids,
					"z": z,
				}
				items.append(block_item)
				z += 1
			pages.append(items)
	finally:
		doc.close()
	return pages 