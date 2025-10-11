from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

from .content_state_tracker import OperatorRecord
from .span_extractor import SpanRecord


@dataclass
class SpanSlice:
    span: SpanRecord
    span_start: int
    span_end: int


def align_records_to_spans(
    records: Sequence[OperatorRecord],
    spans: Sequence[SpanRecord],
) -> Dict[int, List[SpanSlice]]:
    """Map operator records to the spans that cover their text."""

    alignment: Dict[int, List[SpanSlice]] = {}
    if not records or not spans:
        return alignment

    span_slices, full_span_text = _build_span_slices(spans)

    search_pos = 0

    for record in records:
        fragments = record.text_fragments or []
        text = _normalize("".join(fragments))
        if not text:
            continue

        position = full_span_text.find(text, search_pos)
        match_length = len(text)

        if position == -1:
            partial = _find_partial_match(full_span_text, text, search_pos)
            if partial is None:
                continue
            position, match_length = partial

        span_segments = _collect_segments(span_slices, position, position + match_length)
        if span_segments:
            alignment[record.index] = span_segments
            search_pos = position + match_length

    return alignment


def _build_span_slices(
    spans: Sequence[SpanRecord],
) -> tuple[List[tuple[int, int, SpanRecord, str]], str]:
    slices: List[tuple[int, int, SpanRecord, str]] = []
    cursor = 0
    full_text_parts: List[str] = []

    for span in spans:
        text = span.normalized_text if hasattr(span, "normalized_text") else _normalize(span.text or "")
        length = len(text)
        start = cursor
        end = start + length
        slices.append((start, end, span, text))
        full_text_parts.append(text)
        cursor = end

    full_text = "".join(full_text_parts)

    return slices, full_text


def _collect_segments(
    span_slices: Sequence[tuple[int, int, SpanRecord, str]],
    start: int,
    end: int,
) -> List[SpanSlice]:
    segments: List[SpanSlice] = []
    remaining_start = start
    remaining_end = end

    for slice_start, slice_end, span, slice_text in span_slices:
        if slice_end <= remaining_start:
            continue
        if slice_start >= remaining_end:
            break

        local_start = max(remaining_start, slice_start) - slice_start
        local_end = min(remaining_end, slice_end) - slice_start

        grapheme_adjusted_start, grapheme_adjusted_end = _adjust_to_graphemes(span, local_start, local_end)

        segments.append(
            SpanSlice(
                span=span,
                span_start=grapheme_adjusted_start,
                span_end=grapheme_adjusted_end,
            )
        )

        if slice_end >= remaining_end:
            break

    return segments


_ZERO_WIDTH = {
    "\u200B",  # zero-width space
    "\u200C",
    "\u200D",
    "\u2060",
    "\u2061",
    "\u2062",
    "\u2063",
    "\ufeff",
}

_LIGATURE_MAP = {
    "\u000b": "ff",
    "\u000c": "fi",
    "\u000d": "fl",
    "\u000e": "ffi",
    "\u000f": "ffl",
}


def _normalize(text: str) -> str:
    if not text:
        return ""
    expanded: List[str] = []
    for ch in text:
        expanded.append(_LIGATURE_MAP.get(ch, ch))

    filtered = [ch for segment in expanded for ch in segment if ch not in _ZERO_WIDTH]
    normalized: List[str] = []
    previous_was_space = False
    for ch in filtered:
        if ch.isspace():
            if not previous_was_space:
                normalized.append(" ")
            previous_was_space = True
        else:
            normalized.append(ch)
            previous_was_space = False
    return "".join(normalized)


def _adjust_to_graphemes(span: SpanRecord, start: int, end: int) -> Tuple[int, int]:
    if end <= start:
        return start, end
    slices = getattr(span, "grapheme_slices", [])
    if not slices:
        return start, end

    adjusted_start = start
    adjusted_end = end

    for glyph, g_start, g_end in slices:
        if g_end <= start:
            continue
        adjusted_start = g_start
        break

    for glyph, g_start, g_end in slices:
        if g_start < end <= g_end:
            adjusted_end = g_end
            break

    return adjusted_start, adjusted_end


def _find_partial_match(
    full_text: str,
    target: str,
    start_pos: int,
    *,
    min_length: int = 16,
) -> Optional[Tuple[int, int]]:
    length = len(target)
    if length < min_length:
        return None

    # Try prefix windows decreasing in size until we find a match.
    for window in range(length, min_length - 1, -1):
        prefix = target[:window]
        position = full_text.find(prefix, start_pos)
        if position == -1:
            position = full_text.find(prefix)
        if position != -1:
            return position, window

    return None
