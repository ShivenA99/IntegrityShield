from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Set

from .content_state_tracker import OperatorRecord
from .span_alignment import SpanSlice


@dataclass
class ReplacementPlan:
    page_index: int
    original_text: str
    replacement_text: str
    segments: List["ReplacementSegment"]


@dataclass
class ReplacementSegment:
    operator_index: int
    role: str  # prefix | match | suffix
    text: str
    local_start: int
    local_end: int
    span_slices: List[SpanSlice]
    matrix: Tuple[float, float, float, float, float, float]
    font_resource: Optional[str]
    font_size: float
    width: float
    target_start: Optional[int] = None
    target_end: Optional[int] = None
    literal_kind: Optional[str] = None
    requires_isolation: bool = False
    replacement_start: Optional[int] = None
    replacement_end: Optional[int] = None
    slice_max_extents: List[Tuple[int, int]] = field(default_factory=list)
    operator_fragments: List[Dict[str, Any]] = field(default_factory=list)
    planned_replacement: str = ""


Matrix = Tuple[float, float, float, float, float, float]

_IDENTITY_MATRIX: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def build_replacement_plan(
    page_index: int,
    target_text: str,
    replacement_text: str,
    operator_sequence: Sequence[OperatorRecord],
    alignment: Dict[int, List[SpanSlice]],
) -> Optional[ReplacementPlan]:
    """Create a plan describing how the target text maps to operator records."""

    combined = []
    ranges: List[tuple[int, int, OperatorRecord]] = []
    cursor = 0

    for record in operator_sequence:
        text = "".join(record.text_fragments or [])
        if not text:
            continue
        start = cursor
        end = start + len(text)
        combined.append(text)
        ranges.append((start, end, record))
        cursor = end

    full_text = "".join(combined)
    if not target_text or not full_text:
        return None

    match_start = full_text.find(target_text)
    if match_start == -1:
        normalized_target = "".join(ch for ch in target_text if not ch.isspace())
        collapsed_text, index_map = _collapse_stream_text(full_text)
        if normalized_target:
            collapsed_index = collapsed_text.find(normalized_target)
            if collapsed_index == -1:
                return None
            if collapsed_index >= len(index_map):
                return None
            match_start = index_map[collapsed_index]
            end_index = collapsed_index + len(normalized_target) - 1
            if end_index >= len(index_map):
                match_end = len(full_text)
            else:
                match_end = index_map[end_index] + 1
            target_text = full_text[match_start:match_end]
        else:
            return None
    else:
        match_end = match_start + len(target_text)

    segments: List[ReplacementSegment] = []

    for start, end, record in ranges:
        overlap_start = max(match_start, start)
        overlap_end = min(match_end, end)
        if overlap_start >= overlap_end:
            continue

        local_start = overlap_start - start
        local_end = overlap_end - start
        record_text = "".join(record.text_fragments or [])
        slice_list = alignment.get(record.index, [])
        operator_fragments = _extract_operator_fragments(record)
        if local_start > 0:
            prefix_slices, prefix_extents = _slice_span_slices(slice_list, 0, local_start)
            if prefix_slices:
                segments.append(
                    _build_segment(
                        record,
                        role="prefix",
                        text=record_text[:local_start],
                        local_start=0,
                        local_end=local_start,
                        span_slices=prefix_slices,
                        slice_extents=prefix_extents,
                        replacement_start=None,
                        replacement_end=None,
                        operator_fragments=operator_fragments,
                    )
                )

        match_slices, match_extents = _slice_span_slices(slice_list, local_start, local_end)
        if (
            match_slices
            and local_start > 0
            and record_text[:local_start].isspace()
            and slice_list
        ):
            adjusted_slices: List[SpanSlice] = []
            for idx, slice_item in enumerate(match_slices):
                original_slice = slice_list[idx] if idx < len(slice_list) else slice_item
                offset = slice_item.span_start - original_slice.span_start
                if offset > 0:
                    new_start = original_slice.span_start
                    new_end = original_slice.span_end
                    adjusted_slices.append(
                        SpanSlice(
                            span=slice_item.span,
                            span_start=new_start,
                            span_end=new_end,
                        )
                    )
                else:
                    adjusted_slices.append(slice_item)
            match_slices = adjusted_slices
        if match_slices:
            target_start = overlap_start - match_start
            target_end = overlap_end - match_start
            replacement_slice = replacement_text[target_start:target_end] if replacement_text else ""
            force_isolation = (
                record.literal_kind == "array"
                and replacement_slice == ""
                and local_end > local_start
            )

            match_segments = _build_match_segments(
                record,
                record_text,
                match_slices,
                match_extents,
                local_start,
                local_end,
                target_start,
                target_end,
                replacement_text,
                force_isolation,
                operator_fragments,
            )
            segments.extend(match_segments)

        if local_end < len(record_text):
            suffix_slices, suffix_extents = _slice_span_slices(slice_list, local_end, len(record_text))
            if suffix_slices:
                segments.append(
                    _build_segment(
                        record,
                        role="suffix",
                        text=record_text[local_end:],
                        local_start=local_end,
                        local_end=len(record_text),
                        span_slices=suffix_slices,
                        slice_extents=suffix_extents,
                        replacement_start=None,
                        replacement_end=None,
                        operator_fragments=operator_fragments,
                    )
                )

    segments = [segment for segment in segments if segment.text]

    match_segments = [segment for segment in segments if segment.role == "match"]
    if match_segments:
        lengths = [max(0, int(segment.local_end - segment.local_start)) for segment in match_segments]
        pieces = _allocate_replacement_segments(replacement_text or "", lengths) if lengths else []
        if len(pieces) < len(match_segments):
            pieces.extend([""] * (len(match_segments) - len(pieces)))
        cursor = 0
        for segment, piece in zip(match_segments, pieces):
            piece = piece or ""
            start = cursor
            end = start + len(piece)
            cursor = end
            segment.planned_replacement = piece
            segment.replacement_start = start
            segment.replacement_end = end
            segment.target_start = start
            segment.target_end = end
        if cursor < len(replacement_text or "") and match_segments:
            extra = (replacement_text or "")[cursor:]
            if extra:
                last_segment = match_segments[-1]
                last_segment.planned_replacement += extra
                last_segment.replacement_end += len(extra)
                last_segment.target_end = last_segment.replacement_end

    if not segments:
        return None

    return ReplacementPlan(
        page_index=page_index,
        original_text=target_text,
        replacement_text=replacement_text,
        segments=segments,
    )


def _collapse_stream_text(text: str) -> Tuple[str, List[int]]:
    collapsed_chars: List[str] = []
    index_map: List[int] = []
    for idx, ch in enumerate(text):
        if ch.isspace():
            continue
        collapsed_chars.append(ch)
        index_map.append(idx)
    return "".join(collapsed_chars), index_map


def _slice_span_slices(
    span_slices: Sequence[SpanSlice],
    start: int,
    end: int,
) -> Tuple[List[SpanSlice], List[Tuple[int, int]]]:
    if end <= start:
        return [], []

    result: List[SpanSlice] = []
    extents: List[Tuple[int, int]] = []
    consumed = 0
    for slice_item in span_slices:
        length = slice_item.span_end - slice_item.span_start
        if length <= 0:
            continue

        seg_start = consumed
        seg_end = consumed + length
        consumed = seg_end

        if seg_end <= start:
            continue
        if seg_start >= end:
            break

        clip_start = max(start, seg_start)
        clip_end = min(end, seg_end)
        offset_start = clip_start - seg_start
        offset_end = clip_end - seg_start

        new_start = slice_item.span_start + offset_start
        new_end = slice_item.span_start + offset_end

        result.append(
            SpanSlice(
                span=slice_item.span,
                span_start=new_start,
                span_end=new_end,
            )
        )
        extents.append((slice_item.span_start, slice_item.span_end))

        if seg_end >= end:
            break

    return result, extents


def _build_segment(
    record: OperatorRecord,
    role: str,
    text: str,
    local_start: int,
    local_end: int,
    span_slices: List[SpanSlice],
    slice_extents: Optional[Sequence[Tuple[int, int]]],
    replacement_start: Optional[int],
    replacement_end: Optional[int],
    *,
    operator_fragments: Optional[Sequence[Dict[str, Any]]] = None,
    force_isolation: bool = False,
) -> ReplacementSegment:
    matrix = _compute_matrix(span_slices)
    matrix = _maybe_use_record_matrix(
        record,
        span_slices,
        matrix,
        local_start,
        local_end,
    )
    width = _compute_width(span_slices)
    font_resource = record.font_resource
    font_size = record.font_size
    literal_kind = _infer_literal_kind(record, local_start, local_end)

    return ReplacementSegment(
        operator_index=record.index,
        role=role,
        text=text,
        local_start=local_start,
        local_end=local_end,
        span_slices=span_slices,
        matrix=matrix,
        font_resource=font_resource,
        font_size=font_size,
        width=width,
        target_start=replacement_start,
        target_end=replacement_end,
        literal_kind=literal_kind,
        requires_isolation=force_isolation,
        replacement_start=replacement_start,
        replacement_end=replacement_end,
        slice_max_extents=list(slice_extents or []),
        operator_fragments=[dict(fragment) for fragment in operator_fragments] if operator_fragments else [],
    )


def _build_match_segments(
    record: OperatorRecord,
    record_text: str,
    span_slices: Sequence[SpanSlice],
    slice_extents: Sequence[Tuple[int, int]],
    local_start: int,
    local_end: int,
    target_start: int,
    target_end: int,
    replacement_text: str,
    force_isolation: bool,
    operator_fragments: Sequence[Dict[str, Any]],
) -> List[ReplacementSegment]:
    grouped_slices = _group_span_slices_with_extents(span_slices, slice_extents)
    literal_ranges = _collect_literal_ranges(record)

    segments_data: List[Tuple[List[SpanSlice], List[Tuple[int, int]], int, int]] = []
    original_offset = 0

    for group_slices, group_extents in grouped_slices:
        group_length = _span_slice_length(group_slices)
        group_local_start = local_start + original_offset
        group_local_end = group_local_start + group_length

        sub_ranges = _split_group_by_literals(
            literal_ranges,
            group_local_start,
            group_local_end,
        )

        if not sub_ranges:
            sub_ranges = [(group_local_start, group_local_end)]

        for sub_start, sub_end in sub_ranges:
            if sub_end <= sub_start:
                continue
            clipped_slices = _clip_span_slices(
                group_slices,
                group_extents,
                group_local_start,
                sub_start,
                sub_end,
            )
            clipped_list, clipped_extents = clipped_slices
            segments_data.append((clipped_list, clipped_extents, sub_start, sub_end))

        original_offset += group_length

    if not segments_data:
        segments_data.append((list(span_slices), list(slice_extents or []), local_start, local_end))

    replacement_slice = replacement_text[target_start:target_end] if replacement_text else ""
    lengths = [end - start for _, _, start, end in segments_data]
    replacement_pieces = _allocate_replacement_segments(replacement_slice, lengths)

    segments: List[ReplacementSegment] = []
    replacement_cursor = target_start

    for index, (group_slices, group_extents, segment_start, segment_end) in enumerate(segments_data):
        piece = replacement_pieces[index] if index < len(replacement_pieces) else ""
        piece_start = replacement_cursor
        piece_end = piece_start + len(piece)
        replacement_cursor = piece_end

        segments.append(
            _build_segment(
                record,
                role="match",
                text=record_text[segment_start:segment_end],
                local_start=segment_start,
                local_end=segment_end,
                span_slices=group_slices,
                slice_extents=group_extents,
                replacement_start=piece_start,
                replacement_end=piece_end,
                operator_fragments=operator_fragments,
                force_isolation=force_isolation,
            )
        )

    return segments


def _compute_matrix(span_slices: Sequence[SpanSlice]) -> Matrix:
    if not span_slices:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    first_slice = span_slices[0]
    span = first_slice.span
    index = max(0, min(first_slice.span_end - 1, first_slice.span_start))
    chars = span.normalized_chars if span.normalized_chars else span.characters
    if not chars:
        return span.matrix
    index = max(0, min(len(chars) - 1, index))
    _, bbox = chars[index]

    dx, dy = span.direction
    length = math.hypot(dx, dy) or 1.0
    dx /= length
    dy /= length
    scale = span.font_size or 0.0

    a = dx * scale
    b = dy * scale
    c = -dy * scale
    d = dx * scale
    e = bbox[0]
    f = bbox[1]
    return (a, b, c, d, e, f)


def _compute_width(span_slices: Sequence[SpanSlice]) -> float:
    width = 0.0
    for slice_item in span_slices:
        span = slice_item.span
        chars = span.normalized_chars if span.normalized_chars else span.characters
        if not chars:
            continue
        for index in range(slice_item.span_start, min(slice_item.span_end, len(chars))):
            _, bbox = chars[index]
            width += max(0.0, float(bbox[2]) - float(bbox[0]))
    return width


def _infer_literal_kind(
    record: OperatorRecord,
    local_start: int,
    local_end: int,
) -> Optional[str]:
    if not record.text_fragments:
        base_kind = record.literal_kind
        if base_kind in {"text", "byte"}:
            return base_kind
        return None

    fragments = record.text_fragments
    operand_types = record.operand_types or []
    string_types: List[str] = [
        entry.split(":", 1)[-1] if entry.startswith("string") else ""
        for entry in operand_types
        if entry.startswith("string")
    ]

    if not string_types and record.literal_kind in {"text", "byte"}:
        string_types = [record.literal_kind] * len(fragments)

    cursor = 0
    literals: Set[str] = set()

    for index, fragment in enumerate(fragments):
        start = cursor
        end = cursor + len(fragment)
        cursor = end

        if local_end <= start or local_start >= end:
            continue

        literal = None
        if index < len(string_types):
            literal = string_types[index] or None

        if not literal and record.literal_kind in {"text", "byte"}:
            literal = record.literal_kind

        if literal in {"text", "byte"}:
            literals.add(literal)
        else:
            literals.add("mixed")

    if len(literals) == 1:
        literal = literals.pop()
        if literal in {"text", "byte"}:
            return literal
    return None


def _group_span_slices_with_extents(
    span_slices: Sequence[SpanSlice],
    slice_extents: Sequence[Tuple[int, int]],
) -> List[Tuple[List[SpanSlice], List[Tuple[int, int]]]]:
    groups: List[Tuple[List[SpanSlice], List[Tuple[int, int]]]] = []
    current_slices: List[SpanSlice] = []
    current_extents: List[Tuple[int, int]] = []
    current_span = None

    for index, slice_item in enumerate(span_slices):
        extent = slice_extents[index] if index < len(slice_extents) else (slice_item.span_start, slice_item.span_end)
        if current_span is None or slice_item.span is current_span:
            current_slices.append(slice_item)
            current_extents.append(extent)
        else:
            groups.append((current_slices, current_extents))
            current_slices = [slice_item]
            current_extents = [extent]
        current_span = slice_item.span

    if current_slices:
        groups.append((current_slices, current_extents))

    return groups


def _group_span_slices(span_slices: Sequence[SpanSlice]) -> List[List[SpanSlice]]:
    grouped = _group_span_slices_with_extents(
        span_slices,
        [(slice_item.span_start, slice_item.span_end) for slice_item in span_slices],
    )
    return [group for group, _ in grouped]


def _span_slice_length(span_group: Sequence[SpanSlice]) -> int:
    return sum(max(0, slice_item.span_end - slice_item.span_start) for slice_item in span_group)


def _allocate_replacement_segments(
    replacement_slice: str,
    lengths: Sequence[int],
) -> List[str]:
    if not lengths:
        return []

    normalized = [max(0, int(length)) for length in lengths]
    count = len(normalized)
    total_length = sum(normalized)
    remaining_chars = len(replacement_slice)
    remaining_lengths = total_length
    cursor = 0
    pieces: List[str] = []

    for index, length in enumerate(normalized):
        remaining_positive = sum(1 for value in normalized[index + 1 :] if value > 0)
        if index == count - 1:
            slice_text = replacement_slice[cursor:]
        else:
            if remaining_lengths > 0:
                proportional = int(remaining_chars * (length / remaining_lengths))
            else:
                slots = max(count - index, 1)
                proportional = remaining_chars // slots

            max_allowed = max(0, remaining_chars - remaining_positive)
            proportional = max(0, min(proportional, max_allowed))
            if length > 0 and proportional == 0 and remaining_chars > remaining_positive:
                proportional = 1

            slice_text = replacement_slice[cursor : cursor + proportional]

        pieces.append(slice_text)
        consumed = len(slice_text)
        cursor += consumed
        remaining_chars = max(0, remaining_chars - consumed)
        remaining_lengths = max(0, remaining_lengths - length)

    if pieces:
        combined = "".join(pieces)
        if combined != replacement_slice:
            pieces[-1] = pieces[-1] + replacement_slice[len(combined) :]

    return pieces


def _collect_literal_ranges(record: OperatorRecord) -> List[Tuple[int, int, Optional[str]]]:
    ranges: List[Tuple[int, int, Optional[str]]] = []
    fragments = record.text_fragments or []
    operand_types = record.operand_types or []
    string_types: List[Optional[str]] = []

    for entry in operand_types:
        if entry.startswith("string"):
            _, _, suffix = entry.partition(":")
            string_types.append(suffix or None)

    if not string_types and record.literal_kind in {"text", "byte"}:
        string_types = [record.literal_kind] * len(fragments)

    cursor = 0
    for index, fragment in enumerate(fragments):
        start = cursor
        end = cursor + len(fragment)
        cursor = end

        literal = None
        if index < len(string_types):
            literal = string_types[index]

        if not literal and record.literal_kind in {"text", "byte"}:
            literal = record.literal_kind

        ranges.append((start, end, literal))

    return ranges


def _split_group_by_literals(
    literal_ranges: Sequence[Tuple[int, int, Optional[str]]],
    start: int,
    end: int,
) -> List[Tuple[int, int]]:
    segments: List[Tuple[int, int]] = []
    cursor = start

    for literal_start, literal_end, _ in literal_ranges:
        if literal_end <= start or literal_start >= end:
            continue

        overlap_start = max(start, literal_start)
        overlap_end = min(end, literal_end)
        if overlap_end <= overlap_start:
            continue

        if overlap_start > cursor:
            segments.append((cursor, overlap_start))

        segments.append((overlap_start, overlap_end))
        cursor = overlap_end

    if cursor < end:
        segments.append((cursor, end))

    if not segments:
        return []

    return [segment for segment in segments if segment[1] > segment[0]]


def _clip_span_slices(
    span_group: Sequence[SpanSlice],
    extent_group: Sequence[Tuple[int, int]],
    group_start: int,
    segment_start: int,
    segment_end: int,
) -> Tuple[List[SpanSlice], List[Tuple[int, int]]]:
    if segment_end <= segment_start:
        return [], []

    relative_start = segment_start - group_start
    relative_end = segment_end - group_start
    if relative_start < 0:
        relative_start = 0
    if relative_end < relative_start:
        relative_end = relative_start

    clipped: List[SpanSlice] = []
    extents: List[Tuple[int, int]] = []
    consumed = 0

    for index, slice_item in enumerate(span_group):
        length = max(0, slice_item.span_end - slice_item.span_start)
        if length <= 0:
            continue

        slice_start = consumed
        slice_end = consumed + length
        consumed = slice_end

        if slice_end <= relative_start or slice_start >= relative_end:
            continue

        overlap_start = max(relative_start, slice_start)
        overlap_end = min(relative_end, slice_end)
        if overlap_end <= overlap_start:
            continue

        offset_start = overlap_start - slice_start
        offset_end = overlap_end - slice_start

        base_extent = extent_group[index] if index < len(extent_group) else (slice_item.span_start, slice_item.span_end)

        clipped.append(
            SpanSlice(
                span=slice_item.span,
                span_start=slice_item.span_start + offset_start,
                span_end=slice_item.span_start + offset_end,
            )
        )
        extents.append(base_extent)

    if clipped:
        return clipped, extents

    if not span_group:
        return [], []

    base = span_group[0]
    base_extent = extent_group[0] if extent_group else (base.span_start, base.span_end)
    offset_start = max(0, relative_start)
    offset_end = max(offset_start, relative_end)

    return (
        [
            SpanSlice(
                span=base.span,
                span_start=base.span_start + offset_start,
                span_end=base.span_start + offset_end,
            )
        ],
        [base_extent],
    )


def _extract_operator_fragments(record: OperatorRecord) -> List[Dict[str, Any]]:
    fragments = list(record.text_fragments or [])
    raw_bytes = list(record.raw_bytes or [])
    adjustments = list(record.text_adjustments or [])
    operand_types = list(record.operand_types or [])

    if not operand_types and fragments:
        operand_types = ["string"] * len(fragments)

    result: List[Dict[str, Any]] = []
    text_index = 0
    raw_index = 0
    adjustment_index = 0
    cursor = 0

    for op_index, operand_type in enumerate(operand_types):
        entry: Dict[str, Any] = {"index": op_index}
        literal_kind: Optional[str] = None
        if operand_type.startswith("string"):
            literal_kind = operand_type.split(":", 1)[1] if ":" in operand_type else record.literal_kind
            text_value = fragments[text_index] if text_index < len(fragments) else ""
            raw_value = raw_bytes[raw_index] if raw_index < len(raw_bytes) else b""
            entry.update(
                {
                    "type": "string",
                    "literal_kind": literal_kind or record.literal_kind,
                    "text": text_value,
                    "raw_bytes_hex": raw_value.hex() if raw_value else None,
                    "text_start": cursor,
                    "text_end": cursor + len(text_value),
                }
            )
            cursor += len(text_value)
            text_index += 1
            raw_index += 1
        elif operand_type == "number":
            value = adjustments[adjustment_index] if adjustment_index < len(adjustments) else 0.0
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                numeric_value = 0.0
            entry.update(
                {
                    "type": "number",
                    "adjustment": numeric_value,
                    "text_start": cursor,
                    "text_end": cursor,
                }
            )
            adjustment_index += 1
        else:
            entry.update(
                {
                    "type": operand_type,
                    "text_start": cursor,
                    "text_end": cursor,
                }
            )

        result.append({key: value for key, value in entry.items() if value is not None})

    while text_index < len(fragments):
        text_value = fragments[text_index]
        raw_value = raw_bytes[text_index] if text_index < len(raw_bytes) else b""
        entry = {
            "index": len(result),
            "type": "string",
            "literal_kind": record.literal_kind,
            "text": text_value,
            "raw_bytes_hex": raw_value.hex() if raw_value else None,
            "text_start": cursor,
            "text_end": cursor + len(text_value),
        }
        cursor += len(text_value)
        text_index += 1
        result.append({key: value for key, value in entry.items() if value is not None})

    while adjustment_index < len(adjustments):
        value = adjustments[adjustment_index]
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = 0.0
        entry = {
            "index": len(result),
            "type": "number",
            "adjustment": numeric_value,
            "text_start": cursor,
            "text_end": cursor,
        }
        adjustment_index += 1
        result.append(entry)

    return result


def _maybe_use_record_matrix(
    record: OperatorRecord,
    span_slices: Sequence[SpanSlice],
    current: Matrix,
    local_start: int,
    local_end: int,
) -> Matrix:
    fallback = _fallback_matrix_from_record(record, local_start, local_end)
    if fallback is None:
        return current

    if not span_slices:
        return fallback

    if _matrix_is_identity(current):
        return fallback

    if _is_zero_translation(current) and not _is_zero_translation(fallback):
        return fallback

    return current


def _fallback_matrix_from_record(
    record: OperatorRecord,
    local_start: int,
    local_end: int,
) -> Optional[Matrix]:
    matrix_source: Optional[Sequence[float]] = None
    text = "".join(record.text_fragments or [])
    total_length = len(text)

    if record.text_matrix is not None:
        matrix_source = record.text_matrix

    if total_length > 0 and local_start >= total_length and record.post_text_matrix is not None:
        matrix_source = record.post_text_matrix
    elif total_length > 0 and local_start > 0 and local_end >= total_length and record.post_text_matrix is not None:
        matrix_source = record.post_text_matrix
    elif matrix_source is None and record.post_text_matrix is not None:
        matrix_source = record.post_text_matrix

    if matrix_source is None:
        return None

    try:
        values = [float(value) for value in matrix_source]
    except (TypeError, ValueError):
        return None

    if len(values) < 6:
        return None

    return tuple(values[:6])  # type: ignore[return-value]


def _matrix_is_identity(matrix: Matrix, tolerance: float = 1e-6) -> bool:
    return all(abs(matrix[idx] - _IDENTITY_MATRIX[idx]) <= tolerance for idx in range(6))


def _is_zero_translation(matrix: Matrix, tolerance: float = 1e-6) -> bool:
    return abs(matrix[4]) <= tolerance and abs(matrix[5]) <= tolerance
