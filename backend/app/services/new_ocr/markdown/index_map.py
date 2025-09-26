from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _build_span_chain(page: Dict[str, Any], block: Dict[str, Any]) -> List[Tuple[str, str]]:
	"""Return ordered list of (span_id, span_text) for the block by walking children."""
	id_to_item = {it.get("id"): it for it in (page.get("items", []) or [])}
	spans: List[Tuple[str, str]] = []
	for ln_id in block.get("children", []) or []:
		ln = id_to_item.get(ln_id)
		if not ln:
			continue
		for sp_id in (ln.get("children", []) or []):
			sp = id_to_item.get(sp_id)
			if not sp:
				continue
			spans.append((sp_id, sp.get("text", "")))
	return spans


def build_markdown_and_index(page: Dict[str, Any]) -> None:
	"""Mutate page.items by adding markdown/index_map for text_block items based on child span texts.
	If block.markdown already exists, keep it; otherwise use block.text.
	"""
	for item in page.get("items", []) or []:
		if item.get("type") == "text_block":
			text_src = (item.get("markdown") or item.get("text") or "")
			item["markdown"] = text_src
			spans = _build_span_chain(page, item)
			index_map: List[Dict[str, Any]] = []
			if spans:
				cur = 0
				span_ranges: List[Tuple[str, int, int]] = []
				for sp_id, sp_text in spans:
					length = len(sp_text or "")
					span_ranges.append((sp_id, cur, cur + length))
					cur += length
				index_map.append({
					"md_start": 0,
					"md_end": len(text_src),
					"spans": span_ranges,
				})
			else:
				# Fallback: map entire text to the block id
				index_map.append({"md_start": 0, "md_end": len(text_src), "spans": [(item.get("id"), 0, len(text_src))]})
			item["index_map"] = index_map 