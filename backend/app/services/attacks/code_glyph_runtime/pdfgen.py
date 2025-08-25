from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import logging

from ..config import get_base_font_path
from .metrics import ensure_metrics, get_advance_px

logger = logging.getLogger(__name__)


def _add_wrapped_text(page, text: str, top_left: tuple[float, float], width: float, fontname: str = "helv", fontsize: float = 11, color=(0, 0, 0)) -> float:
	x, y = top_left
	max_chars = max(10, int(width // (fontsize * 0.5)))
	for raw_line in (text.splitlines() or [text]):
		line = raw_line.strip()
		while line:
			chunk = line[:max_chars]
			cut = chunk.rfind(" ")
			if cut > 0 and len(line) > max_chars:
				chunk = line[:cut]
			page.insert_text((x, y), chunk, fontname=fontname, fontsize=fontsize, color=color)
			y += fontsize + 2
			line = line[len(chunk):].lstrip()
	return y


def _pair_font_key(in_code: int, out_code: int) -> str:
	return f"U+{in_code:04X}_to_U+{out_code:04X}"


def _pair_font_path(prebuilt_dir: Path, in_code: int, out_code: int) -> Path:
	return prebuilt_dir / f"map_U+{in_code:04X}_to_U+{out_code:04X}.ttf"


def _ensure_base_font(page, base_font_path: Optional[Path]) -> str:
	if base_font_path and base_font_path.exists():
		try:
			page.insert_font(fontname="DejaVuSans", fontfile=str(base_font_path))
			logger.info("[code_glyph.pdfgen] Embedded base font via page.insert_font: %s", base_font_path)
			return "DejaVuSans"
		except Exception as e:
			logger.warning("[code_glyph.pdfgen] Failed to embed base font %s: %s", base_font_path, e)
	return "helv"


def _ensure_pair_font(page, prebuilt_dir: Path, in_code: int, out_code: int) -> Optional[str]:
	key = _pair_font_key(in_code, out_code)
	font_path = _pair_font_path(prebuilt_dir, in_code, out_code)
	if not font_path.exists():
		logger.warning("[code_glyph.pdfgen] Missing pair font: %s", font_path)
		return None
	try:
		page.insert_font(fontname=key, fontfile=str(font_path))
		logger.info("[code_glyph.pdfgen] Pair font ready %s -> %s at %s (fontname=%s)", f"U+{in_code:04X}", f"U+{out_code:04X}", font_path, key)
		return key
	except Exception as e:
		logger.warning("[code_glyph.pdfgen] Failed to insert pair font %s: %s", font_path, e)
		return None


def _draw_mapped_sequence(page, x: float, y: float, fontsize: float, base_font: str, prebuilt_dir: Path,
							input_entity: str, output_entity: str, *, reverse: bool = False,
							metrics: Optional[Dict] = None, base_font_path: Optional[Path] = None,
							margin_left: float = 0.0, right_edge: float = 1e9, leading: float = 14.0) -> Tuple[float, float]:
	max_len = max(len(input_entity), len(output_entity))
	for i in range(max_len):
		in_char = input_entity[i] if i < len(input_entity) else ""
		out_char = output_entity[i] if i < len(output_entity) else ""
		in_code = ord(in_char) if in_char else None
		out_code = ord(out_char) if out_char else None

		if not reverse:
			# Original direction (not used now but kept for completeness)
			if in_code is None:
				in_char = "\u200B"; in_code = 0x200B
			if out_code is None:
				out_char = "\u200B"; out_code = 0x200B
			fontname = _ensure_pair_font(page, prebuilt_dir, in_code, out_code)
			draw_char = in_char if fontname else out_char
			use_font = fontname or base_font
			# measure advance before drawing for wrap decision
			if metrics and base_font_path:
				font_path = _pair_font_path(prebuilt_dir, in_code, out_code) if fontname else base_font_path
				adv = get_advance_px(metrics, font_path, ord(draw_char), fontsize, fallback_paths=[base_font_path])
			else:
				adv = fontsize * 0.6
			if x + adv > right_edge:
				x = margin_left
				y += leading
			page.insert_text((x, y), draw_char, fontname=use_font, fontsize=fontsize, color=(0, 0, 0))
			logger.info("[code_glyph.pdfgen] map pos=%d in=%s(U+%04X) → out=%s(U+%04X) using=%s adv=%.2f",
						i, repr(in_char), in_code, repr(out_char), out_code, use_font, adv)
			x += adv
		else:
			# Reversed: draw output codepoint with out->in font so extraction=output, visual=input
			if out_code is not None and in_code is not None:
				fontname = _ensure_pair_font(page, prebuilt_dir, out_code, in_code)
				draw_char = out_char
				use_font = fontname or base_font
				if metrics and base_font_path:
					font_path = _pair_font_path(prebuilt_dir, out_code, in_code) if fontname else base_font_path
					adv = get_advance_px(metrics, font_path, out_code, fontsize, fallback_paths=[base_font_path])
				else:
					adv = fontsize * 0.6
				if x + adv > right_edge:
					x = margin_left
					y += leading
				page.insert_text((x, y), draw_char, fontname=use_font, fontsize=fontsize, color=(0, 0, 0))
				logger.info("[code_glyph.pdfgen] reverse map pos=%d out=%s(U+%04X) → in=%s(U+%04X) using=%s adv=%.2f",
						i, repr(out_char), out_code, repr(in_char), in_code, use_font, adv)
				x += adv
			elif in_code is not None and out_code is None:
				# extra input (pad visually) via 200B->in
				zw = "\u200B"; zw_code = 0x200B
				fontname = _ensure_pair_font(page, prebuilt_dir, zw_code, in_code)
				draw_char = zw
				use_font = fontname or base_font
				if metrics and base_font_path:
					font_path = _pair_font_path(prebuilt_dir, zw_code, in_code) if fontname else base_font_path
					adv = get_advance_px(metrics, font_path, zw_code, fontsize, fallback_paths=[base_font_path])
				else:
					adv = fontsize * 0.55
				if x + adv > right_edge:
					x = margin_left
					y += leading
				page.insert_text((x, y), draw_char, fontname=use_font, fontsize=fontsize, color=(0, 0, 0))
				logger.info("[code_glyph.pdfgen] reverse map pos=%d pad vis in=%s(U+%04X) via U+200B using=%s adv=%.2f",
						i, repr(input_entity[i]), in_code, use_font, adv)
				x += adv
			elif out_code is not None and in_code is None:
				# extra output (hide visually) via out->200B
				fontname = _ensure_pair_font(page, prebuilt_dir, out_code, 0x200B)
				draw_char = out_char
				use_font = fontname or base_font
				if metrics and base_font_path:
					font_path = _pair_font_path(prebuilt_dir, out_code, 0x200B) if fontname else base_font_path
					adv = get_advance_px(metrics, font_path, out_code, fontsize, fallback_paths=[base_font_path])
				else:
					adv = fontsize * 0.55
				if x + adv > right_edge:
					x = margin_left
					y += leading
				page.insert_text((x, y), draw_char, fontname=use_font, fontsize=fontsize, color=(0, 0, 0))
				logger.info("[code_glyph.pdfgen] reverse map pos=%d pad out=%s(U+%04X) → U+200B using=%s adv=%.2f",
						i, repr(out_char), out_code, use_font, adv)
				x += adv
	return x, y


def render_attacked_pdf(title: str, questions: List[Dict], entities_by_qnum: Dict[str, Dict[str, str]], output_path: Path, prebuilt_dir: Path) -> Path:
	logger.info("[code_glyph.pdfgen] Starting render; output=%s", output_path)
	output_path.parent.mkdir(parents=True, exist_ok=True)

	doc = fitz.open()
	page = doc.new_page()
	width, height = page.rect.br

	margin = 54.0
	y = margin

	# Title
	title_text = title or "Attacked Assessment (Code Glyph)"
	page.insert_text((margin, y), title_text, fontname="helv", fontsize=16, color=(0, 0, 0))
	y += 28

	# Base font
	base_font_path = get_base_font_path()
	base_font = _ensure_base_font(page, base_font_path)

	# Load or build metrics once
	metrics = ensure_metrics(prebuilt_dir, base_font_path)

	def _draw_text_chunk(page, x: float, y: float, text: str, font: str, fontsize: float, margin_left: float, right_edge: float, leading: float) -> Tuple[float, float]:
		# width-aware wrapping (breaks long words); returns updated (x, y)
		if not text:
			return x, y
		for ch in text:
			if ch == "\n":
				x = margin_left
				y += leading
				continue
			# measure char advance
			if base_font_path and metrics:
				cp = ord(ch)
				adv = get_advance_px(metrics, base_font_path, cp, fontsize)
			else:
				adv = fontsize * 0.6
			if x + adv > right_edge:
				x = margin_left
				y += leading
			page.insert_text((x, y), ch, fontname=font, fontsize=fontsize, color=(0, 0, 0))
			x += adv
		return x, y

	def _render_stem_with_inline_mapping(page, stem: str, y: float, base_font: str, fontsize: float, in_ent: str, out_ent: str) -> float:
		margin_left = margin
		usable_width = width - 2 * margin
		right_edge = margin_left + usable_width
		leading = fontsize + 4
		for raw_line in (stem.splitlines() or [stem]):
			x = margin_left
			line = raw_line
			if in_ent:
				start = 0
				while True:
					idx = line.find(in_ent, start)
					if idx == -1:
						# draw remainder
						rem = line[start:]
						x, y = _draw_text_chunk(page, x, y, rem, base_font, fontsize, margin_left, right_edge, leading)
						break
					# draw text before match
					before = line[start:idx]
					x, y = _draw_text_chunk(page, x, y, before, base_font, fontsize, margin_left, right_edge, leading)
					# draw mapped segment inline (width-aware)
					logger.info("[code_glyph.pdfgen] Inline map at col=%d in_entity='%s' out_entity='%s'", idx, in_ent, out_ent)
					x, y = _draw_mapped_sequence(
						page, x, y, fontsize=fontsize, base_font=base_font, prebuilt_dir=prebuilt_dir,
						input_entity=in_ent, output_entity=out_ent, reverse=True,
						metrics=metrics, base_font_path=base_font_path,
						margin_left=margin_left, right_edge=right_edge, leading=leading,
					)
					start = idx + len(in_ent)
				y += leading
			else:
				# no mapping entity; draw normally
				x, y = _draw_text_chunk(page, x, y, line, base_font, fontsize, margin_left, right_edge, leading)
				y += leading
		return y

	for q in questions:
		qnum = str(q.get("q_number"))
		stem = q.get("attacked_stem") or q.get("stem_text") or ""
		ents = entities_by_qnum.get(qnum, {})

		if y > height - margin * 2:
			page = doc.new_page()
			y = margin

		# Question header
		page.insert_text((margin, y), f"Q{qnum}.", fontname=base_font, fontsize=13, color=(0, 0, 0))
		y += 18

		# Stem with inline mapping
		in_entity = ents.get("input_entity", "")
		out_entity = ents.get("output_entity", "")
		y = _render_stem_with_inline_mapping(page, stem, y, base_font, 11, in_entity, out_entity)
		y += 2

		# Options if present
		opts = q.get("options") or {}
		if opts:
			for label, text in opts.items():
				if y > height - margin * 2:
					page = doc.new_page()
					y = margin
				# draw wrapped option text
				opt_fontsize = 10
				leading = opt_fontsize + 4
				x_opt = margin + 16
				right_edge = width - margin
				option_text = f"{label}) {text}"
				x_opt, y = _draw_text_chunk(page, x_opt, y, option_text, base_font, opt_fontsize, x_opt, right_edge, leading)
				y += leading
			y += 4

	logger.info("[code_glyph.pdfgen] Saving PDF to %s", output_path)
	doc.save(str(output_path))
	doc.close()
	logger.info("[code_glyph.pdfgen] Render complete: %s", output_path)
	return output_path 