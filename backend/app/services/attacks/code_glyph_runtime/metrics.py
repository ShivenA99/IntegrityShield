from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

try:
	from fontTools.ttLib import TTFont  # type: ignore
except Exception:  # pragma: no cover
	TTFont = None  # type: ignore

logger = logging.getLogger(__name__)


def _compute_font_metrics_for_file(font_path: Path) -> Optional[Dict[str, Any]]:
	if TTFont is None:
		logger.error("[code_glyph.metrics] fonttools not available; cannot compute metrics for %s", font_path)
		return None
	try:
		tt = TTFont(str(font_path))
		head = tt.get("head")
		hhea = tt.get("hhea")
		hmtx = tt.get("hmtx")
		cmap_tbl = tt.get("cmap")
		if not (head and hhea and hmtx and cmap_tbl):
			logger.warning("[code_glyph.metrics] Missing tables in %s; skipping", font_path)
			return None
		units_per_em = int(getattr(head, "unitsPerEm", 1000))

		# Merge cmaps
		codepoint_to_glyph: Dict[int, str] = {}
		for sub in cmap_tbl.tables:
			try:
				for cp, gn in sub.cmap.items():
					codepoint_to_glyph[cp] = gn
			except Exception:
				continue

		advances: Dict[str, int] = {}
		for cp, glyph_name in codepoint_to_glyph.items():
			try:
				aw, _lsb = hmtx.metrics.get(glyph_name, (getattr(hhea, "advanceWidthMax", 0), 0))
				advances[f"U+{cp:04X}"] = int(aw)
			except Exception:
				continue

		logger.info("[code_glyph.metrics] Computed metrics: %s (UPM=%d, glyphs=%d)", font_path, units_per_em, len(advances))
		return {"unitsPerEm": units_per_em, "advances": advances}
	except Exception as e:
		logger.warning("[code_glyph.metrics] Failed to compute metrics for %s: %s", font_path, e)
		return None


def build_and_save_metrics(prebuilt_dir: Path, base_font_path: Optional[Path]) -> Dict[str, Any]:
	prebuilt_dir = prebuilt_dir.resolve()
	metrics: Dict[str, Any] = {"version": 1, "fonts": {}}

	# Base font first
	if base_font_path and base_font_path.exists():
		base_font_path = base_font_path.resolve()
		base_metrics = _compute_font_metrics_for_file(base_font_path)
		if base_metrics:
			metrics["fonts"][str(base_font_path)] = base_metrics

	# All pair fonts
	for ttf in prebuilt_dir.rglob("*.ttf"):
		m = _compute_font_metrics_for_file(ttf)
		if m:
			metrics["fonts"][str(ttf.resolve())] = m

	metrics_path = prebuilt_dir / "font_metrics.json"
	try:
		with open(metrics_path, "w", encoding="utf-8") as f:
			json.dump(metrics, f, indent=2, ensure_ascii=False)
		logger.info("[code_glyph.metrics] Saved font metrics to %s (fonts=%d)", metrics_path, len(metrics["fonts"]))
	except Exception as e:
		logger.warning("[code_glyph.metrics] Failed to save metrics to %s: %s", metrics_path, e)

	return metrics


def load_metrics(prebuilt_dir: Path) -> Optional[Dict[str, Any]]:
	metrics_path = prebuilt_dir.resolve() / "font_metrics.json"
	if metrics_path.exists():
		try:
			with open(metrics_path, "r", encoding="utf-8") as f:
				data = json.load(f)
			if isinstance(data, dict) and "fonts" in data:
				logger.info("[code_glyph.metrics] Loaded font metrics from %s (fonts=%d)", metrics_path, len(data.get("fonts", {})))
				return data
		except Exception as e:
			logger.warning("[code_glyph.metrics] Failed to load metrics from %s: %s", metrics_path, e)
	return None


def ensure_metrics(prebuilt_dir: Path, base_font_path: Optional[Path]) -> Dict[str, Any]:
	loaded = load_metrics(prebuilt_dir)
	if loaded:
		return loaded
	logger.info("[code_glyph.metrics] Metrics not found; computing once and persisting under %s", prebuilt_dir)
	return build_and_save_metrics(prebuilt_dir, base_font_path)


def get_advance_px(metrics: Dict[str, Any], font_path: Path, codepoint: int, fontsize: float, *, fallback_paths: Optional[list[Path]] = None) -> float:
	font_key = str(font_path.resolve())
	font_info = metrics.get("fonts", {}).get(font_key)
	if font_info:
		units_per_em = max(1, int(font_info.get("unitsPerEm", 1000)))
		advances = font_info.get("advances", {})
		adv_units = advances.get(f"U+{codepoint:04X}")
		if isinstance(adv_units, int):
			return (adv_units / units_per_em) * fontsize
	# fallback to alternative fonts (e.g., base font)
	if fallback_paths:
		for fp in fallback_paths:
			px = get_advance_px(metrics, fp, codepoint, fontsize, fallback_paths=None)
			if px is not None:
				return px
	# as a last resort, return a conservative width
	return fontsize * 0.5 