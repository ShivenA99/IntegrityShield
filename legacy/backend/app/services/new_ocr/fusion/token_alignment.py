from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from ..utils.geometry import iou, nfkc, normalize_ws

logger = logging.getLogger(__name__)


def _levenshtein(a: str, b: str) -> int:
	a = a or ""; b = b or ""
	la, lb = len(a), len(b)
	if la == 0: return lb
	if lb == 0: return la
	d = [[0] * (lb + 1) for _ in range(la + 1)]
	for i in range(la + 1): d[i][0] = i
	for j in range(lb + 1): d[0][j] = j
	for i in range(1, la + 1):
		for j in range(1, lb + 1):
			cost = 0 if a[i - 1] == b[j - 1] else 1
			d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
	return d[la][lb]


def _norm(s: str) -> str:
	return normalize_ws(nfkc(s or "")).strip()


def align_tokens(local_spans: List[Dict[str, Any]], ocr_tokens: List[Dict[str, Any]]) -> List[Tuple[int, int, float]]:
	"""Return list of (local_idx, ocr_idx, score) matches.
	Score blends IoU and normalized edit-similarity.
	"""
	pairs: List[Tuple[int, int, float]] = []
	for i, sp in enumerate(local_spans):
		bbox = tuple(sp.get("bbox", (0, 0, 0, 0)))
		st = _norm(sp.get("text", ""))
		best = (-1, -1, -1.0)
		for j, tok in enumerate(ocr_tokens):
			tb = tuple(tok.get("bbox", (0, 0, 0, 0)))
			ts = _norm(tok.get("text", ""))
			j_iou = iou(bbox, tb)
			if not ts and not st and j_iou <= 0: continue
			ld = _levenshtein(st, ts)
			max_len = max(1, max(len(st), len(ts)))
			edit_sim = 1.0 - (ld / max_len)
			score = 0.6 * j_iou + 0.4 * edit_sim
			if score > best[2]:
				best = (i, j, score)
		if best[2] >= 0.2:
			pairs.append(best)
	return pairs 