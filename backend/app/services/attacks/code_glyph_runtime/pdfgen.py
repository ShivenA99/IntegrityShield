from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import logging

from ..config import get_base_font_path
from .metrics import ensure_metrics, get_advance_px

logger = logging.getLogger(__name__)

# Cache for fitz.Font objects by absolute font path
_font_obj_cache: Dict[str, "fitz.Font"] = {}


def _match_case_pattern(source: str, target: str) -> str:
    """Return target adjusted to match the casing pattern of source.

    - All upper -> upper
    - All lower -> lower
    - Titlecase -> Titlecase
    - Mixed -> per-character mapping when possible, else leave as-is for extra chars
    """
    if not source or not target:
        return target
    if source.isupper():
        return target.upper()
    if source.islower():
        return target.lower()
    if source.istitle():
        return target[:1].upper() + target[1:].lower()
    # Mixed case: apply char-wise
    out_chars: List[str] = []
    for i, ch in enumerate(target):
        if i < len(source) and source[i].isalpha():
            out_chars.append(ch.upper() if source[i].isupper() else ch.lower())
        else:
            out_chars.append(ch)
    return "".join(out_chars)


def _get_font_obj(font_path: Path | None) -> "fitz.Font":
	import fitz  # lazy
	if font_path and font_path.exists():
		key = str(font_path.resolve())
		fo = _font_obj_cache.get(key)
		if fo is None:
			fo = fitz.Font(fontfile=str(font_path))
			_font_obj_cache[key] = fo
		return fo
	# Fallback to built-in Helvetica
	return fitz.Font(fontname="helv")


def _draw_text_chunk(page, x: float, y: float, text: str, font: str, fontsize: float, margin_left: float, right_edge: float, leading: float, *, metrics: Optional[Dict] = None, base_font_path: Optional[Path] = None) -> Tuple[float, float]:
	# width-aware wrapping (breaks long words); returns updated (x, y)
	if not text:
		return x, y
	for ch in text:
		if ch == "\n":
			x = margin_left
			y += leading
			continue
		# measure char advance
		if metrics and base_font_path:
			try:
				from .metrics import get_advance_px
				cp = ord(ch)
				adv = get_advance_px(metrics, base_font_path, cp, fontsize)
			except Exception:
				adv = fontsize * 0.6
		else:
			adv = fontsize * 0.6
		if x + adv > right_edge:
			x = margin_left
			y += leading
		page.insert_text((x, y), ch, fontname=font, fontsize=fontsize, color=(0, 0, 0))
		x += adv
	return x, y


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
				# If identity mapping, use base font directly
				if out_code == in_code:
					use_font = base_font
					draw_char = out_char
					if metrics and base_font_path:
						adv = get_advance_px(metrics, base_font_path, out_code, fontsize, fallback_paths=[base_font_path])
					else:
						adv = fontsize * 0.6
					if x + adv > right_edge:
						x = margin_left
						y += leading
					page.insert_text((x, y), draw_char, fontname=use_font, fontsize=fontsize, color=(0, 0, 0))
					logger.info("[code_glyph.pdfgen] reverse map pos=%d identity out=%s(U+%04X) using base=%s adv=%.2f",
							i, repr(out_char), out_code, use_font, adv)
					x += adv
					continue
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
				# extra input (pad vis) via 2009->in (thin space with non-zero advance)
				hs = "\u2009"; hs_code = 0x2009
				fontname = _ensure_pair_font(page, prebuilt_dir, hs_code, in_code)
				draw_char = hs
				use_font = fontname or base_font
				if metrics and base_font_path:
					font_path = _pair_font_path(prebuilt_dir, hs_code, in_code) if fontname else base_font_path
					adv = get_advance_px(metrics, font_path, hs_code, fontsize, fallback_paths=[base_font_path])
				else:
					adv = fontsize * 0.4
				if x + adv > right_edge:
					x = margin_left
					y += leading
				page.insert_text((x, y), draw_char, fontname=use_font, fontsize=fontsize, color=(0, 0, 0))
				logger.info("[code_glyph.pdfgen] reverse map pos=%d pad vis in=%s(U+%04X) via U+2009 using=%s adv=%.2f",
						i, repr(input_entity[i]), in_code, use_font, adv)
				x += adv
			elif out_code is not None and in_code is None:
				# extra output (thin visible spacer) via out->2009
				fontname = _ensure_pair_font(page, prebuilt_dir, out_code, 0x2009)
				draw_char = out_char
				use_font = fontname or base_font
				if metrics and base_font_path:
					font_path = _pair_font_path(prebuilt_dir, out_code, 0x2009) if fontname else base_font_path
					adv = get_advance_px(metrics, font_path, out_code, fontsize, fallback_paths=[base_font_path])
				else:
					adv = fontsize * 0.4
				if x + adv > right_edge:
					x = margin_left
					y += leading
				page.insert_text((x, y), draw_char, fontname=use_font, fontsize=fontsize, color=(0, 0, 0))
				logger.info("[code_glyph.pdfgen] reverse map pos=%d pad out=%s(U+%04X) → U+2009 using=%s adv=%.2f",
						i, repr(out_char), out_code, use_font, adv)
				x += adv
	return x, y


def draw_mapped_token_at(page, x: float, y: float, token_in: str, token_out: str, *, fontsize: float, base_font: str, prebuilt_dir: Path, metrics: Optional[Dict] = None, base_font_path: Optional[Path] = None, right_edge: float = 1e9, leading: float = 14.0) -> Tuple[float, float]:
	"""Render a single token as ONE text object using a TextWriter so extractors keep inline order.

	Extraction should yield token_out. Visual should look like token_in.
	"""
	import fitz  # PyMuPDF
	logger.info("[code_glyph.pdfgen] Drawing mapped token (writer) at (%.2f,%.2f) in='%s' out='%s' pt=%.2f", x, y, token_in, token_out, fontsize)
	# Prepare writer
	w = fitz.TextWriter(page.rect)
	# Prepare base font object
	base_font_obj = _get_font_obj(base_font_path if base_font_path and base_font_path.exists() else None)

	def _get_metric(field: str, font_path: Optional[Path]) -> Optional[float]:
		try:
			if not metrics or not font_path:
				return None
			fi = metrics.get("fonts", {}).get(str(font_path.resolve()))
			if not isinstance(fi, dict):
				return None
			val = fi.get(field)
			return float(val) if isinstance(val, (int, float)) and float(val) > 0 else None
		except Exception:
			return None

	def _size_factor_for_pair(pair_path: Optional[Path]) -> float:
		# Compute base_xH/pair_xH (fallback to capHeight) and clamp to ±2%
		bx = _get_metric("xHeight", base_font_path)
		px = _get_metric("xHeight", pair_path)
		if not bx or not px:
			bx = bx or _get_metric("capHeight", base_font_path)
			px = px or _get_metric("capHeight", pair_path)
		if not bx or not px or px <= 0:
			return 1.0
		factor = bx / px
		lo, hi = 0.98, 1.02
		if factor < lo:
			return lo
		if factor > hi:
			return hi
		return factor
	# Case-align the output to the input token's casing
	if token_in:
		token_out = _match_case_pattern(token_in, token_out)

	# Build glyph runs across max length with padding for mismatches
	glyphs: list[tuple[fitz.Font, str, float, float]] = []  # (font_obj, char, fontsize_char, advance_px)
	advances: list[float] = []
	cumul: list[float] = []
	n_in = len(token_in or "")
	n_out = len(token_out or "")
	max_len = max(n_in, n_out)
	for i in range(max_len):
		in_code: Optional[int] = ord(token_in[i]) if i < n_in else None
		out_code: Optional[int] = ord(token_out[i]) if i < n_out else None

		# Three cases:
		# 1) Both chars present: draw out_code mapped to in_code (reverse) so extract=out, visual=in
		# 2) Extra input (visual longer): draw U+2009 mapped to in_code (visible, space-like semantics)
		# 3) Extra output (parsed longer): draw out_code mapped to U+200B (zero-width visual)
		if in_code is not None and out_code is not None:
			if out_code == in_code:
				font_obj = base_font_obj
				fontsize_char = fontsize
				font_path_for_width = base_font_path
			else:
				pair_path = _pair_font_path(prebuilt_dir, out_code, in_code)  # type: ignore[arg-type]
				font_obj = _get_font_obj(pair_path if pair_path.exists() else (base_font_path if base_font_path else None))
				fontsize_char = fontsize * (_size_factor_for_pair(pair_path if pair_path.exists() else None))
				font_path_for_width = pair_path if pair_path.exists() else base_font_path
			ch = chr(out_code)
			try:
				adv = font_obj.text_length(ch, fontsize_char)
			except Exception:
				adv = get_advance_px(metrics, font_path_for_width, out_code, fontsize_char, fallback_paths=[base_font_path]) if (metrics and font_path_for_width) else max(0.4, fontsize_char * 0.6)
			glyphs.append((font_obj, ch, fontsize_char, adv))
			advances.append(adv)
			cumul.append((cumul[-1] if cumul else 0.0) + adv)
		elif in_code is not None and out_code is None:
			# Extra input: pad with thin-space codepoint U+2009 mapped to the input glyph for visible width
			pad_code = 0x2009
			pair_path = _pair_font_path(prebuilt_dir, pad_code, in_code)
			font_obj = _get_font_obj(pair_path if pair_path.exists() else (base_font_path if base_font_path else None))
			fontsize_char = fontsize * (_size_factor_for_pair(pair_path if pair_path.exists() else None))
			font_path_for_width = pair_path if pair_path.exists() else base_font_path
			ch = chr(pad_code)
			try:
				adv = font_obj.text_length(ch, fontsize_char)
			except Exception:
				adv = get_advance_px(metrics, font_path_for_width, pad_code, fontsize_char, fallback_paths=[base_font_path]) if (metrics and font_path_for_width) else max(0.3, fontsize_char * 0.4)
			glyphs.append((font_obj, ch, fontsize_char, adv))
			advances.append(adv)
			cumul.append((cumul[-1] if cumul else 0.0) + adv)
		elif out_code is not None and in_code is None:
			# Extra output: map to zero-width space U+200B so parser sees the char but visual width is ~0
			pad_zero_code = 0x200B
			pair_path = _pair_font_path(prebuilt_dir, out_code, pad_zero_code)
			font_obj = _get_font_obj(pair_path if pair_path.exists() else (base_font_path if base_font_path else None))
			# Keep size aligned; but advance should be ~0 when pair exists; fallback to minimal
			fontsize_char = fontsize * (_size_factor_for_pair(pair_path if pair_path.exists() else None))
			ch = chr(out_code)
			try:
				adv = font_obj.text_length(ch, fontsize_char)
			except Exception:
				# If we cannot measure (or pair missing), force near-zero advance
				adv = 0.0
			glyphs.append((font_obj, ch, fontsize_char, adv))
			advances.append(adv)
			cumul.append((cumul[-1] if cumul else 0.0) + adv)

	if not glyphs:
		return x, y

	desired_width = max(0.0, (right_edge - x))
	total_out = cumul[-1] if cumul else 0.0
	# Compute x positions: compress if wider, distribute gaps if narrower, center single glyph
	x_positions: list[float] = []
	if total_out > desired_width and desired_width > 0:
		scale_x = max(0.0, desired_width / total_out)
		for i in range(len(glyphs)):
			nat_x = (0.0 if i == 0 else cumul[i - 1])
			x_positions.append(x + scale_x * nat_x)
	elif total_out <= desired_width and desired_width > 0:
		n_gaps = max(0, len(glyphs) - 1)
		if n_gaps > 0:
			gap_extra = (desired_width - total_out) / n_gaps
			for i in range(len(glyphs)):
				nat_x = (0.0 if i == 0 else cumul[i - 1])
				x_positions.append(x + nat_x + gap_extra * i)
		else:
			# single glyph: center within box
			x_positions.append(x + (desired_width - total_out) / 2.0)
	else:
		# No right_edge bound; use natural positions
		for i in range(len(glyphs)):
			nat_x = (0.0 if i == 0 else cumul[i - 1])
			x_positions.append(x + nat_x)

	# Ensure last glyph fits within right_edge by tiny correction if needed
	try:
		last_x = x_positions[-1]
		last_adv = advances[-1]
		if last_x + last_adv > right_edge:
			overflow = (last_x + last_adv) - right_edge
			shift = overflow
			for i in range(len(x_positions)):
				x_positions[i] = x_positions[i] - shift * (i / max(1, len(x_positions) - 1))
	except Exception:
		pass

	# Append all glyphs to the writer as a single run
	for i, (font_obj, ch, fsz, _adv) in enumerate(glyphs):
		w.append((x_positions[i], y), ch, font=font_obj, fontsize=fsz)

	# Emit the text
	w.write_text(page)

	# Diagnostics
	try:
		logger.info("[code_glyph.pdfgen] positioned token width fit: desired=%.2f total=%.2f pos_first=%.2f pos_last=%.2f", desired_width, total_out, x_positions[0], x_positions[-1])
	except Exception:
		pass

	return x_positions[-1] + (advances[-1] if advances else 0.0), y


def _render_text_with_mappings(page, text: str, y: float, base_font: str, fontsize: float, prebuilt_dir: Path,
								 mappings: List[Dict[str, str]], *, metrics: Optional[Dict] = None, base_font_path: Optional[Path] = None,
								 margin_left: float, right_edge: float, leading: float) -> float:
	# Render a line-oriented text block applying multiple inline mappings.
	if not text:
		return y
	for raw_line in (text.splitlines() or [text]):
		x = margin_left
		line = raw_line
		start = 0
		while True:
			# Find earliest next match among all mappings
			earliest_idx = -1
			chosen = None
			for m in mappings:
				inp = m.get("input_entity") or ""
				out = m.get("output_entity") or ""
				if not inp:
					continue
				idx = line.find(inp, start)
				if idx != -1 and (earliest_idx == -1 or idx < earliest_idx):
					earliest_idx = idx
					chosen = (inp, out)
			if earliest_idx == -1 or chosen is None:
				# draw remainder and break line
				rem = line[start:]
				x, y = _draw_text_chunk(page, x, y, rem, base_font, fontsize, margin_left, right_edge, leading, metrics=metrics, base_font_path=base_font_path)
				break
			# draw text before match
			before = line[start:earliest_idx]
			x, y = _draw_text_chunk(page, x, y, before, base_font, fontsize, margin_left, right_edge, leading, metrics=metrics, base_font_path=base_font_path)
			# draw mapped segment
			in_ent, out_ent = chosen
			# Case-align output to the actual matched input segment
			seg_in = line[earliest_idx:earliest_idx + len(in_ent)]
			out_ent = _match_case_pattern(seg_in, out_ent)
			logger.info("[code_glyph.pdfgen] Inline multi-map at col=%d in='%s' out='%s'", earliest_idx, in_ent, out_ent)
			x, y = _draw_mapped_sequence(
				page, x, y, fontsize=fontsize, base_font=base_font, prebuilt_dir=prebuilt_dir,
				input_entity=in_ent, output_entity=out_ent, reverse=True,
				metrics=metrics, base_font_path=base_font_path,
				margin_left=margin_left, right_edge=right_edge, leading=leading,
			)
			start = earliest_idx + len(in_ent)
		y += leading
	return y


def _render_text_with_mappings_clipped(page, text: str, y: float, base_font: str, fontsize: float, prebuilt_dir: Path,
										 mappings: List[Dict[str, str]], *, metrics: Optional[Dict] = None, base_font_path: Optional[Path] = None,
										 margin_left: float, right_edge: float, leading: float, y_max: float) -> float:
	# Same as _render_text_with_mappings but will not draw beyond y_max.
	if not text:
		return y
	for raw_line in (text.splitlines() or [text]):
		if y > y_max:
			break
		x = margin_left
		line = raw_line
		start = 0
		while True:
			if y > y_max:
				break
			# Find earliest next match among all mappings
			earliest_idx = -1
			chosen = None
			for m in mappings:
				inp = m.get("input_entity") or ""
				out = m.get("output_entity") or ""
				if not inp:
					continue
				idx = line.find(inp, start)
				if idx != -1 and (earliest_idx == -1 or idx < earliest_idx):
					earliest_idx = idx
					chosen = (inp, out)
			if earliest_idx == -1 or chosen is None:
				# draw remainder and break line
				rem = line[start:]
				x, y = _draw_text_chunk(page, x, y, rem, base_font, fontsize, margin_left, right_edge, leading, metrics=metrics, base_font_path=base_font_path)
				break
			# draw text before match
			before = line[start:earliest_idx]
			x, y = _draw_text_chunk(page, x, y, before, base_font, fontsize, margin_left, right_edge, leading, metrics=metrics, base_font_path=base_font_path)
			# draw mapped segment
			in_ent, out_ent = chosen
			seg_in = line[earliest_idx:earliest_idx + len(in_ent)]
			out_ent = _match_case_pattern(seg_in, out_ent)
			logger.info("[code_glyph.pdfgen] Inline multi-map at col=%d in='%s' out='%s'", earliest_idx, in_ent, out_ent)
			x, y = _draw_mapped_sequence(
				page, x, y, fontsize=fontsize, base_font=base_font, prebuilt_dir=prebuilt_dir,
				input_entity=in_ent, output_entity=out_ent, reverse=True,
				metrics=metrics, base_font_path=base_font_path,
				margin_left=margin_left, right_edge=right_edge, leading=leading,
			)
			start = earliest_idx + len(in_ent)
		y_next = y + leading
		if y_next > y_max:
			return y
		y = y_next
	return y


def measure_text_with_mappings(text: str, fontsize: float, prebuilt_dir: Path, mappings: List[Dict[str, str]], *, metrics: Optional[Dict] = None, base_font_path: Optional[Path] = None, width: float) -> Tuple[float, int]:
	"""Return (height_px, line_count) for rendering text with mappings within the given width.

	Uses the same wrapping decisions as _render_text_with_mappings/_draw_text_chunk.
	"""
	margin_left = 0.0
	right_edge = width
	leading = fontsize + 4
	line_count = 0
	y = 0.0
	if not text:
		return 0.0, 0
	for raw_line in (text.splitlines() or [text]):
		x = margin_left
		line = raw_line
		start = 0
		while True:
			# Find earliest next match among all mappings
			earliest_idx = -1
			chosen = None
			for m in mappings:
				inp = m.get("input_entity") or ""
				if not inp:
					continue
				idx = line.find(inp, start)
				if idx != -1 and (earliest_idx == -1 or idx < earliest_idx):
					earliest_idx = idx
					chosen = m
			if earliest_idx == -1 or chosen is None:
				# draw/measure remainder and break line
				rem = line[start:]
				# measure base text chunk
				for ch in rem:
					if ch == "\n":
						x = margin_left
						y += leading
						line_count += 1
						continue
					if metrics and base_font_path:
						try:
							adv = get_advance_px(metrics, base_font_path, ord(ch), fontsize)
						except Exception:
							adv = fontsize * 0.6
					else:
						adv = fontsize * 0.6
					if x + adv > right_edge:
						x = margin_left
						y += leading
						line_count += 1
					x += adv
				break
			# measure before chunk
			before = line[start:earliest_idx]
			for ch in before:
				if ch == "\n":
					x = margin_left
					y += leading
					line_count += 1
					continue
				if metrics and base_font_path:
					try:
						adv = get_advance_px(metrics, base_font_path, ord(ch), fontsize)
					except Exception:
						adv = fontsize * 0.6
				else:
					adv = fontsize * 0.6
				if x + adv > right_edge:
					x = margin_left
					y += leading
					line_count += 1
				x += adv
			# measure mapped segment (approximate using base font advances for output chars)
			out_ent = (chosen.get("output_entity") or "")
			for ch in out_ent:
				if metrics and base_font_path:
					try:
						adv = get_advance_px(metrics, base_font_path, ord(ch), fontsize)
					except Exception:
						adv = fontsize * 0.6
				else:
					adv = fontsize * 0.6
				if x + adv > right_edge:
					x = margin_left
					y += leading
					line_count += 1
				x += adv
			start = earliest_idx + len(chosen.get("input_entity") or "")
		y += leading
		line_count += 1
	return max(0.0, y), line_count


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

	# use module-level _draw_text_chunk
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
						x, y = _draw_text_chunk(page, x, y, rem, base_font, fontsize, margin_left, right_edge, leading, metrics=metrics, base_font_path=base_font_path)
						break
					# draw text before match
					before = line[start:idx]
					x, y = _draw_text_chunk(page, x, y, before, base_font, fontsize, margin_left, right_edge, leading, metrics=metrics, base_font_path=base_font_path)
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
				x, y = _draw_text_chunk(page, x, y, line, base_font, fontsize, margin_left, right_edge, leading, metrics=metrics, base_font_path=base_font_path)
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
		mappings = ents.get("mappings") if isinstance(ents.get("mappings"), list) else None
		if mappings:
			margin_left = margin
			usable_width = width - 2 * margin
			right_edge = margin_left + usable_width
			leading = 11 + 4
			y = _render_text_with_mappings(page, stem, y, base_font, 11, prebuilt_dir, mappings, metrics=metrics, base_font_path=base_font_path, margin_left=margin_left, right_edge=right_edge, leading=leading)
		else:
			# Case-align mapping when rendering stems
			out_entity_ca = _match_case_pattern(in_entity, out_entity) if in_entity and out_entity else out_entity
			y = _render_stem_with_inline_mapping(page, stem, y, base_font, 11, in_entity, out_entity_ca)
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
				if mappings:
					y = _render_text_with_mappings(page, option_text, y, base_font, opt_fontsize, prebuilt_dir, mappings, metrics=metrics, base_font_path=base_font_path, margin_left=x_opt, right_edge=right_edge, leading=leading)
				else:
					x_opt, y = _draw_text_chunk(page, x_opt, y, option_text, base_font, opt_fontsize, x_opt, right_edge, leading, metrics=metrics, base_font_path=base_font_path)
				y += leading
			y += 4

	logger.info("[code_glyph.pdfgen] Saving PDF to %s", output_path)
	doc.save(str(output_path))
	doc.close()
	logger.info("[code_glyph.pdfgen] Render complete: %s", output_path)
	return output_path 