from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _is_question_text(text: str) -> bool:
	if not text:
		return False
	s = text.strip()
	ls = s.lower()
	return s.startswith("Q") or ls.startswith("question") or ls.startswith("q1") or ls.startswith("q2") or ls.startswith("q3")


def fuse_layout(local_doc: Dict[str, Any], mistral_page: Dict[str, Any], openai_page: Dict[str, Any]) -> Dict[str, Any]:
	"""Fuse local PyMuPDF AST with vendor OCR for one page.
	Copies local items, attaches vendor markdown if any, enriches fields, and ensures spans/lines/blocks children.
	If block-level vendor OCR is available (via item.vendor.{openai,mistral}), keep it; otherwise we fallback to page-level markdown.
	"""
	items_out: List[Dict[str, Any]] = []
	for it in list(local_doc.get("items", [])):
		itype = (it.get("type") or "")
		if itype == "text_block":
			text = it.get("text", "")
			it.setdefault("question_text", _is_question_text(text))
			it.setdefault("render_as", "text")
			# preserve any per-block vendor fields if later steps add them
		elif itype == "text_line":
			it.setdefault("children", it.get("children", []))
		elif itype == "text_span":
			pass
		items_out.append(it)
	page_out = {
		"page_index": local_doc.get("page_index"),
		"width": local_doc.get("width"),
		"height": local_doc.get("height"),
		"dpi": local_doc.get("dpi"),
		"items": items_out,
	}
	vendor_md = (mistral_page or {}).get("markdown") or ""
	alt_md = (openai_page or {}).get("markdown") or ""
	if alt_md and len(alt_md) > len(vendor_md):
		vendor_md = alt_md
	page_out["markdown"] = vendor_md
	return page_out


def build_document(pages_local: List[Dict[str, Any]], pages_mistral: List[Dict[str, Any]], pages_openai: List[Dict[str, Any]]) -> Dict[str, Any]:
	pages: List[Dict[str, Any]] = []
	for i, pl in enumerate(pages_local or []):
		pm = pages_mistral[i] if i < len(pages_mistral) else {}
		po = pages_openai[i] if i < len(pages_openai) else {}
		pages.append(fuse_layout(pl, pm, po))
	return {"pages": pages} 