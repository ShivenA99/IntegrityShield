from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


_MATH_CHARS = set(list("∑∫√≈≠≤≥±∞πθλμσΩ×÷^_{}[]()=+−*/<>"))


def _looks_like_math(text: str) -> bool:
	if not text:
		return False
	if any(ch in _MATH_CHARS for ch in text):
		return True
	# patterns like x^2, a_i, \frac, \sum
	return bool(re.search(r"(\\(frac|sum|int)|\w_\w|\w\^\w)", text))


def detect_hard_regions(page: Dict[str, Any], vendor_page_mistral: Dict[str, Any], vendor_page_openai: Dict[str, Any]) -> List[Dict[str, Any]]:
	"""Return a list of regions to augment with OpenAI Vision.
	Each region: { type: 'math'|'table'|'text', bbox: [x0,y0,x1,y1], page_index, block_id? }
	Heuristics:
	- math: detect math-like text in text_block
	- table: if page has figure/drawings or dense bullets blocks, mark their bbox as table candidates
	- text: blocks with very low vendor confidence (both) or empty vendor markdown
	"""
	regions: List[Dict[str, Any]] = []
	pidx = int(page.get("page_index", 0))
	conf_m = float(vendor_page_mistral.get("confidence", 0.0) or 0.0)
	conf_o = float(vendor_page_openai.get("confidence", 0.0) or 0.0)

	for item in page.get("items", []) or []:
		t = item.get("type")
		bbox = item.get("bbox") or []
		if t == "text_block":
			text = (item.get("text") or "").strip()
			if _looks_like_math(text):
				regions.append({"type": "math", "bbox": bbox, "page_index": pidx, "block_id": item.get("id")})
			elif conf_m < 0.3 and conf_o < 0.3:
				regions.append({"type": "text", "bbox": bbox, "page_index": pidx, "block_id": item.get("id")})
		elif t in {"figure"}:
			regions.append({"type": "table", "bbox": bbox, "page_index": pidx, "block_id": item.get("id")})
		elif t == "image":
			# skip generic images by default
			pass
	return regions 