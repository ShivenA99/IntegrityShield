from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .content_state_tracker import OperatorRecord
from .span_alignment import SpanSlice
from .span_extractor import SpanRecord


@dataclass
class AdvanceMetrics:
    advance: float
    start_projection: float
    end_projection: float
    direction: Tuple[float, float]


def compute_advance_from_spans(
    record: OperatorRecord,
    span_slices: Sequence[SpanSlice],
) -> Optional[AdvanceMetrics]:
    """Compute text advance using span projections along writing direction."""

    if not span_slices:
        return None

    total_advance = 0.0
    last_end_proj: Optional[float] = None
    first_proj: Optional[float] = None
    direction: Optional[Tuple[float, float]] = None

    for slice_info in span_slices:
        span = slice_info.span
        projections = _segment_projections(span, slice_info.span_start, slice_info.span_end)
        if projections is None:
            continue

        seg_min, seg_max, dir_vec = projections
        if seg_min is None or seg_max is None:
            continue

        if direction is None:
            direction = dir_vec

        if first_proj is None:
            first_proj = seg_min

        if last_end_proj is not None:
            gap = seg_min - last_end_proj
            if gap > 0:
                total_advance += gap

        total_advance += max(seg_max - seg_min, 0.0)
        last_end_proj = seg_max

    if last_end_proj is None or first_proj is None or direction is None:
        return None

    return AdvanceMetrics(
        advance=total_advance,
        start_projection=first_proj,
        end_projection=last_end_proj,
        direction=direction,
    )


def _segment_projections(
    span: SpanRecord,
    start: int,
    end: int,
) -> Optional[Tuple[Optional[float], Optional[float], Tuple[float, float]]]:
    if end <= start:
        return None

    chars = span.normalized_chars if span.normalized_chars else _normalize_chars(span.characters)
    if not chars:
        return None

    subset = chars[start:end]
    if not subset:
        return None

    dir_x, dir_y = span.direction
    length = math.hypot(dir_x, dir_y)
    if length <= 1e-6:
        dir_x, dir_y = 1.0, 0.0
        length = 1.0
    dir_x /= length
    dir_y /= length

    min_proj: Optional[float] = None
    max_proj: Optional[float] = None

    for _, bbox in subset:
        points = (
            (bbox[0], bbox[1]),
            (bbox[2], bbox[1]),
            (bbox[0], bbox[3]),
            (bbox[2], bbox[3]),
        )
        for x, y in points:
            projection = x * dir_x + y * dir_y
            if min_proj is None or projection < min_proj:
                min_proj = projection
            if max_proj is None or projection > max_proj:
                max_proj = projection

    return min_proj, max_proj, (dir_x, dir_y)


def _normalize_chars(
    characters: Sequence[Tuple[str, Tuple[float, float, float, float]]]
) -> List[Tuple[str, Tuple[float, float, float, float]]]:
    normalized: List[Tuple[str, Tuple[float, float, float, float]]] = []
    for glyph, bbox in characters:
        if not glyph:
            continue
        if glyph in _ZERO_WIDTH:
            continue
        normalized.append((glyph, bbox))
    return normalized


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
