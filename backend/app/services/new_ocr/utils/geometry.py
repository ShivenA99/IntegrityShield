from __future__ import annotations

from typing import List, Tuple
import unicodedata


def iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
	ax0, ay0, ax1, ay1 = a
	bx0, by0, bx1, by1 = b
	x0 = max(ax0, bx0)
	y0 = max(ay0, by0)
	x1 = min(ax1, bx1)
	y1 = min(ay1, by1)
	w = max(0.0, x1 - x0)
	h = max(0.0, y1 - y0)
	inter = w * h
	area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
	area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
	union = area_a + area_b - inter
	return (inter / union) if union > 0 else 0.0


def nfkc(text: str) -> str:
	return unicodedata.normalize("NFKC", text or "")


def normalize_ws(text: str) -> str:
	return " ".join((text or "").split()) 