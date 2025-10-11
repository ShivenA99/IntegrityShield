from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

import fitz

from .content_state_tracker import (
    ContentStateTracker,
    OperatorRecord,
    combine_with_ctm,
)
from .operator_metrics import AdvanceMetrics, compute_advance_from_spans
from .span_alignment import SpanSlice, align_records_to_spans
from .span_extractor import SpanRecord, collect_span_records


def analyze_page_content(
    content_operations: Sequence[Tuple[Sequence[object], bytes | str]],
    page: fitz.Page,
    page_index: int,
) -> Tuple[
    Sequence[OperatorRecord],
    Sequence[SpanRecord],
    Dict[int, Sequence[SpanSlice]],
]:
    """Run instrumentation over a page and align text operators to spans."""

    initial_tracker = ContentStateTracker()
    preliminary_records = initial_tracker.walk(content_operations)

    spans = collect_span_records(page, page_index)
    alignment = align_records_to_spans(preliminary_records, spans)

    spans_available = bool(spans)

    advance_map: Dict[int, AdvanceMetrics] = {}
    for record in preliminary_records:
        spans_for_record = alignment.get(record.index)
        metrics = None
        if spans_for_record:
            metrics = compute_advance_from_spans(record, spans_for_record)
        if metrics is None:
            metrics = _compute_fallback_metrics(record)
        if metrics is not None:
            advance_map[record.index] = metrics

    def resolver(rec: OperatorRecord, state) -> Optional[float]:
        metrics = advance_map.get(rec.index)
        return metrics.advance if metrics else None

    tracker = ContentStateTracker(advance_resolver=resolver)
    final_records = tracker.walk(content_operations)

    translation_tolerance = 0.5  # points

    recorded_page_warning = False
    missing_alignment_reported = False

    for record in final_records:
        has_text = bool(record.text_fragments)
        if not spans_available:
            if has_text and not recorded_page_warning:
                record.advance_warning = "span extraction unavailable; using naive advance"
                recorded_page_warning = True
            continue
        metrics = advance_map.get(record.index)
        if metrics:
            record.advance = metrics.advance
            record.advance_direction = metrics.direction
            record.advance_start_projection = metrics.start_projection
            record.advance_end_projection = metrics.end_projection

            start_world = combine_with_ctm(record.ctm, record.text_matrix)
            end_matrix = record.post_text_matrix or record.text_matrix
            end_world = combine_with_ctm(record.ctm, end_matrix)

            record.world_start = (start_world[4], start_world[5])
            record.world_end = (end_world[4], end_world[5])

            dx = end_world[4] - start_world[4]
            dy = end_world[5] - start_world[5]
            record.advance_delta = (dx, dy)

            expected_dx = metrics.direction[0] * metrics.advance
            expected_dy = metrics.direction[1] * metrics.advance
            record.advance_error = math.hypot(dx - expected_dx, dy - expected_dy)
            record.suffix_matrix_error = record.advance_error
            if record.advance_error > translation_tolerance:
                record.advance_warning = (
                    f"suffix matrix drift {record.advance_error:.3f}pt exceeds tolerance"
                )
        elif has_text and not missing_alignment_reported:
            record.advance_warning = "missing span alignment; using naive advance"
            missing_alignment_reported = True

    return final_records, spans, alignment


def _compute_fallback_metrics(record: OperatorRecord) -> Optional[AdvanceMetrics]:
    """Synthesize advance metrics from operator state when span alignment fails."""

    if not record.text_fragments:
        return None

    if record.advance is None or record.advance == 0.0:
        return None

    start_matrix = combine_with_ctm(record.ctm, record.text_matrix)

    dir_x = start_matrix[0]
    dir_y = start_matrix[1]
    if abs(dir_x) <= 1e-9 and abs(dir_y) <= 1e-9:
        dir_x = record.ctm[0] * record.text_matrix[2] + record.ctm[2] * record.text_matrix[3]
        dir_y = record.ctm[1] * record.text_matrix[2] + record.ctm[3] * record.text_matrix[3]

    length = math.hypot(dir_x, dir_y)
    if length <= 1e-9:
        dir_x, dir_y = 1.0, 0.0
    else:
        dir_x /= length
        dir_y /= length

    start_x = start_matrix[4]
    start_y = start_matrix[5]
    advance = record.advance

    end_x = start_x + dir_x * advance
    end_y = start_y + dir_y * advance

    start_projection = start_x * dir_x + start_y * dir_y
    end_projection = end_x * dir_x + end_y * dir_y

    return AdvanceMetrics(
        advance=advance,
        start_projection=start_projection,
        end_projection=end_projection,
        direction=(dir_x, dir_y),
    )
