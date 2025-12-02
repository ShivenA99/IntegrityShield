from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import fitz

Matrix = Tuple[float, float, float, float, float, float]


_ZERO_WIDTH = {
    "\u200B",
    "\u200C",
    "\u200D",
    "\u2060",
    "\u2061",
    "\u2062",
    "\u2063",
    "\ufeff",
}


def _identity_matrix() -> Matrix:
    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _locate_glyph_bounds(source: str, glyph: str, start_index: int) -> Tuple[int, int]:
    """Locate the next occurrence of *glyph* in *source* starting from *start_index*.

    Falls back to the provided boundary when an exact match is not found, ensuring
    that downstream text slicing maintains a monotonic progression even with
    ligatures or normalization differences.
    """

    if not glyph:
        clamped = max(0, start_index)
        return clamped, clamped

    text_length = len(source)
    cursor = max(0, min(start_index, text_length))

    position = source.find(glyph, cursor)
    if position == -1:
        position = cursor

    end_pos = position + len(glyph)
    if end_pos < position:
        end_pos = position
    if end_pos > text_length:
        end_pos = text_length

    return position, end_pos


@dataclass
class SpanRecord:
    page_index: int
    block_index: int
    line_index: int
    span_index: int
    text: str
    font: str
    font_size: float
    bbox: Tuple[float, float, float, float]
    origin: Tuple[float, float]
    direction: Tuple[float, float]
    matrix: Matrix
    ascent: float
    descent: float
    characters: List[Tuple[str, Tuple[float, float, float, float]]]
    normalized_text: str
    normalized_chars: List[Tuple[str, Tuple[float, float, float, float]]]
    grapheme_slices: List[Tuple[str, int, int]]
    normalized_to_raw_indices: List[Tuple[int, int]] = field(default_factory=list)


def collect_span_records(page: fitz.Page, page_index: int) -> List[SpanRecord]:
    """Collect spans with inferred text matrices."""
    records: List[SpanRecord] = []

    raw = page.get_text("rawdict") or {}
    if not raw.get("blocks"):
        fallback = page.get_text("dict") or {}
        if fallback.get("blocks"):
            raw = fallback
    blocks = raw.get("blocks", [])

    for block_idx, block in enumerate(blocks):
        lines = block.get("lines", [])
        for line_idx, line in enumerate(lines):
            spans = line.get("spans", [])
            for span_idx, span in enumerate(spans):
                text = span.get("text") or ""
                if not text:
                    char_items = span.get("chars") or []
                    text = "".join(
                        entry.get("c", "")
                        for entry in char_items
                        if entry.get("c") and not entry.get("synthetic", False)
                    )
                if not text:
                    continue
                font = span.get("font") or ""
                try:
                    font_size = float(span.get("size") or 0.0)
                except (TypeError, ValueError):
                    font_size = 0.0
                bbox_raw = span.get("bbox") or [0.0, 0.0, 0.0, 0.0]
                bbox = tuple(float(v) for v in bbox_raw[:4])  # type: ignore[assignment]
                origin_raw = span.get("origin") or [bbox[0], bbox[1]]
                origin = (float(origin_raw[0]), float(origin_raw[1]))
                dir_raw = span.get("dir") or (1.0, 0.0)
                direction = (float(dir_raw[0]), float(dir_raw[1]))
                ascent = float(span.get("ascender") or 0.0)
                descent = float(span.get("descender") or 0.0)

                characters: List[Tuple[str, Tuple[float, float, float, float]]] = []
                for char in span.get("chars", []) or []:
                    if char.get("synthetic"):
                        continue
                    glyph = char.get("c") or ""
                    bbox_char = char.get("bbox") or bbox_raw
                    try:
                        char_bbox = tuple(float(v) for v in bbox_char[:4])  # type: ignore[assignment]
                    except (TypeError, ValueError):
                        char_bbox = bbox
                    characters.append((glyph, char_bbox))

                normalized_chars: List[Tuple[str, Tuple[float, float, float, float]]] = []
                normalized_text_parts: List[str] = []
                grapheme_slices: List[Tuple[str, int, int]] = []
                normalized_to_raw: List[Tuple[int, int]] = []

                cursor = 0
                raw_cursor = 0
                for glyph, glyph_box in characters:
                    if not glyph or glyph in _ZERO_WIDTH:
                        continue
                    normalized_chars.append((glyph, glyph_box))
                    normalized_text_parts.append(glyph)
                    raw_start, raw_end = _locate_glyph_bounds(text, glyph, raw_cursor)
                    normalized_to_raw.append((raw_start, raw_end))
                    start_index = cursor
                    end_index = cursor + 1
                    grapheme_slices.append((glyph, start_index, end_index))
                    cursor = end_index
                    raw_cursor = max(raw_cursor, raw_end)

                normalized_text = "".join(normalized_text_parts)

                matrix = _infer_span_matrix(font_size, origin, direction)

                matrix_raw = span.get("matrix")
                if matrix_raw and len(matrix_raw) == 6:
                    try:
                        matrix = tuple(float(v) for v in matrix_raw)  # type: ignore[assignment]
                    except (TypeError, ValueError):
                        pass

                records.append(
                    SpanRecord(
                        page_index=page_index,
                        block_index=block_idx,
                        line_index=line_idx,
                        span_index=span_idx,
                        text=text,
                        font=font,
                        font_size=font_size,
                        bbox=bbox,
                        origin=origin,
                        direction=direction,
                        matrix=matrix,
                        ascent=ascent,
                        descent=descent,
                        characters=characters,
                        normalized_text=normalized_text,
                        normalized_chars=normalized_chars,
                        grapheme_slices=grapheme_slices,
                        normalized_to_raw_indices=normalized_to_raw,
                    )
                )

    return records


def _infer_span_matrix(
    font_size: float,
    origin: Tuple[float, float],
    direction: Tuple[float, float],
) -> Matrix:
    if font_size == 0:
        return _identity_matrix()

    dx, dy = direction
    scale = font_size

    # Construct a matrix that aligns with the span direction at the origin
    a = dx * scale
    b = dy * scale
    c = -dy * scale
    d = dx * scale
    e, f = origin

    return (a, b, c, d, e, f)
