"""Targeted tests for match planner fallback behaviour."""

from PyPDF2.generic import ByteStringObject

from app.services.pipeline.enhancement_methods.match_planner import build_replacement_plan
from app.services.pipeline.enhancement_methods.content_state_tracker import OperatorRecord
from app.services.pipeline.enhancement_methods.span_alignment import SpanSlice
from app.services.pipeline.enhancement_methods.span_extractor import SpanRecord


def test_hex_only_match_segment_uses_record_matrix_when_span_missing_geometry():
    original_text = "\x01\x02"
    replacement_text = "\x03\x04"

    record = OperatorRecord(
        index=0,
        operator=b"Tj",
        operands=(ByteStringObject(original_text.encode("latin-1")),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 120.0, 540.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 120.0, 540.0),
        font_resource="/F1",
        font_size=10.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=12.0,
        text_rise=0.0,
        text_fragments=[original_text],
        text_adjustments=None,
        operand_types=["string:byte"],
        literal_kind="byte",
        raw_bytes=[original_text.encode("latin-1")],
        advance=None,
        post_text_matrix=(1.0, 0.0, 0.0, 1.0, 140.0, 540.0),
        advance_direction=None,
        advance_start_projection=None,
        advance_end_projection=None,
        advance_delta=None,
        advance_error=None,
        advance_warning=None,
        world_start=None,
        world_end=None,
        suffix_matrix_error=None,
    )

    span = SpanRecord(
        page_index=0,
        block_index=0,
        line_index=0,
        span_index=0,
        text="",
        font="F1",
        font_size=10.0,
        bbox=(0.0, 0.0, 0.0, 0.0),
        origin=(0.0, 0.0),
        direction=(1.0, 0.0),
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        ascent=0.0,
        descent=0.0,
        characters=[],
        normalized_text="",
        normalized_chars=[],
        grapheme_slices=[],
    )

    alignment = {0: [SpanSlice(span=span, span_start=0, span_end=len(original_text))]}

    plan = build_replacement_plan(
        page_index=0,
        target_text=original_text,
        replacement_text=replacement_text,
        operator_sequence=[record],
        alignment=alignment,
    )

    assert plan is not None
    assert plan.segments, "Expected planner to emit segments"

    match_segments = [segment for segment in plan.segments if segment.role == "match"]
    assert match_segments, "Expected match segment for hex-only replacement"

    match_matrix = match_segments[0].matrix
    assert match_matrix == record.text_matrix


def test_match_segments_split_when_spans_have_distinct_matrices():
    original_text = "ABCD"
    replacement_text = "WXYZ"

    record = OperatorRecord(
        index=0,
        operator=b"TJ",
        operands=(ByteStringObject(original_text.encode("latin-1")),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 100.0, 500.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 100.0, 500.0),
        font_resource="/F1",
        font_size=9.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=11.0,
        text_rise=0.0,
        text_fragments=[original_text],
        text_adjustments=None,
        operand_types=["string:byte"],
        literal_kind="array",
        raw_bytes=[original_text.encode("latin-1")],
        advance=None,
        post_text_matrix=(1.0, 0.0, 0.0, 1.0, 140.0, 500.0),
        advance_direction=None,
        advance_start_projection=None,
        advance_end_projection=None,
        advance_delta=None,
        advance_error=None,
        advance_warning=None,
        world_start=None,
        world_end=None,
        suffix_matrix_error=None,
    )

    span_a = SpanRecord(
        page_index=0,
        block_index=0,
        line_index=0,
        span_index=0,
        text="AB",
        font="F1",
        font_size=9.0,
        bbox=(0.0, 0.0, 20.0, 10.0),
        origin=(100.0, 500.0),
        direction=(1.0, 0.0),
        matrix=(9.0, 0.0, -0.0, 9.0, 100.0, 500.0),
        ascent=0.0,
        descent=0.0,
        characters=[("A", (100.0, 500.0, 110.0, 510.0)), ("B", (110.0, 500.0, 120.0, 510.0))],
        normalized_text="AB",
        normalized_chars=[("A", (100.0, 500.0, 110.0, 510.0)), ("B", (110.0, 500.0, 120.0, 510.0))],
        grapheme_slices=[("A", 0, 1), ("B", 1, 2)],
    )

    span_b = SpanRecord(
        page_index=0,
        block_index=0,
        line_index=0,
        span_index=1,
        text="CD",
        font="F1",
        font_size=9.0,
        bbox=(0.0, 0.0, 20.0, 10.0),
        origin=(120.0, 500.0),
        direction=(0.0, 1.0),
        matrix=(0.0, 9.0, -9.0, 0.0, 120.0, 500.0),
        ascent=0.0,
        descent=0.0,
        characters=[("C", (120.0, 500.0, 130.0, 510.0)), ("D", (120.0, 510.0, 130.0, 520.0))],
        normalized_text="CD",
        normalized_chars=[("C", (120.0, 500.0, 130.0, 510.0)), ("D", (120.0, 510.0, 130.0, 520.0))],
        grapheme_slices=[("C", 0, 1), ("D", 1, 2)],
    )

    alignment = {
        0: [
            SpanSlice(span=span_a, span_start=0, span_end=2),
            SpanSlice(span=span_b, span_start=0, span_end=2),
        ]
    }

    plan = build_replacement_plan(
        page_index=0,
        target_text=original_text,
        replacement_text=replacement_text,
        operator_sequence=[record],
        alignment=alignment,
    )

    assert plan is not None
    match_segments = [segment for segment in plan.segments if segment.role == "match"]
    assert len(match_segments) == 2

    first_segment, second_segment = match_segments
    assert first_segment.text == "AB"
    assert second_segment.text == "CD"
    assert first_segment.matrix == span_a.matrix
    assert second_segment.matrix == span_b.matrix

    assert first_segment.target_start == 0
    assert first_segment.target_end == 2
    assert second_segment.target_start == 2
    assert second_segment.target_end == 4


def test_mixed_literal_deletion_forces_isolation_per_fragment():
    original_text = "AA\x01\x02BB"
    target_text = "A\x01\x02B"

    record = OperatorRecord(
        index=0,
        operator=b"TJ",
        operands=(ByteStringObject(original_text.encode("latin-1")),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 20.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 20.0),
        font_resource="/F1",
        font_size=9.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=11.0,
        text_rise=0.0,
        text_fragments=["AA", "\x01\x02", "BB"],
        text_adjustments=None,
        operand_types=["string:text", "string:byte", "string:text"],
        literal_kind="array",
        raw_bytes=[b"AA", b"\x01\x02", b"BB"],
        advance=None,
        post_text_matrix=(1.0, 0.0, 0.0, 1.0, 40.0, 20.0),
        advance_direction=None,
        advance_start_projection=None,
        advance_end_projection=None,
        advance_delta=None,
        advance_error=None,
        advance_warning=None,
        world_start=None,
        world_end=None,
        suffix_matrix_error=None,
    )

    span = SpanRecord(
        page_index=0,
        block_index=0,
        line_index=0,
        span_index=0,
        text=original_text,
        font="F1",
        font_size=9.0,
        bbox=(0.0, 0.0, 60.0, 12.0),
        origin=(10.0, 20.0),
        direction=(1.0, 0.0),
        matrix=(9.0, 0.0, 0.0, 9.0, 10.0, 20.0),
        ascent=0.0,
        descent=0.0,
        characters=[
            (ch, (10.0 + idx * 5.0, 20.0, 15.0 + idx * 5.0, 30.0))
            for idx, ch in enumerate(original_text)
        ],
        normalized_text=original_text,
        normalized_chars=[
            (ch, (10.0 + idx * 5.0, 20.0, 15.0 + idx * 5.0, 30.0))
            for idx, ch in enumerate(original_text)
        ],
        grapheme_slices=[(ch, idx, idx + 1) for idx, ch in enumerate(original_text)],
    )

    alignment = {
        0: [SpanSlice(span=span, span_start=0, span_end=len(original_text))]
    }

    plan = build_replacement_plan(
        page_index=0,
        target_text=target_text,
        replacement_text="",
        operator_sequence=[record],
        alignment=alignment,
    )

    assert plan is not None

    match_segments = [segment for segment in plan.segments if segment.role == "match"]
    assert len(match_segments) == 3

    texts = [segment.text for segment in match_segments]
    assert texts == ["A", "\x01\x02", "B"]

    literal_kinds = [segment.literal_kind for segment in match_segments]
    assert literal_kinds == ["text", "byte", "text"]

    assert all(segment.requires_isolation for segment in match_segments)

    target_ranges = [(segment.target_start, segment.target_end) for segment in match_segments]
    assert target_ranges == [(0, 0), (0, 0), (0, 0)]


def test_segment_records_replacement_offsets_and_fragments_for_tail_growth():
    original_text = "long-term"
    replacement_text = "short-term"

    record = OperatorRecord(
        index=0,
        operator=b"Tj",
        operands=(ByteStringObject(original_text.encode("latin-1")),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        font_resource="/F1",
        font_size=9.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=12.0,
        text_rise=0.0,
        text_fragments=[original_text],
        text_adjustments=None,
        operand_types=["string:text"],
        literal_kind="text",
        raw_bytes=[original_text.encode("latin-1")],
        advance=None,
        post_text_matrix=(1.0, 0.0, 0.0, 1.0, 120.0, 700.0),
        advance_direction=None,
        advance_start_projection=None,
        advance_end_projection=None,
        advance_delta=None,
        advance_error=None,
        advance_warning=None,
        world_start=None,
        world_end=None,
        suffix_matrix_error=None,
    )

    span = SpanRecord(
        page_index=0,
        block_index=0,
        line_index=0,
        span_index=0,
        text=original_text,
        font="F1",
        font_size=9.0,
        bbox=(50.0, 700.0, 110.0, 710.0),
        origin=(50.0, 700.0),
        direction=(1.0, 0.0),
        matrix=(9.0, 0.0, 0.0, 9.0, 50.0, 700.0),
        ascent=0.0,
        descent=0.0,
        characters=[(ch, (50.0 + idx * 5.0, 700.0, 55.0 + idx * 5.0, 710.0)) for idx, ch in enumerate(original_text)],
        normalized_text=original_text,
        normalized_chars=[(ch, (50.0 + idx * 5.0, 700.0, 55.0 + idx * 5.0, 710.0)) for idx, ch in enumerate(original_text)],
        grapheme_slices=[(ch, idx, idx + 1) for idx, ch in enumerate(original_text)],
    )

    alignment = {0: [SpanSlice(span=span, span_start=0, span_end=len(original_text))]}

    plan = build_replacement_plan(
        page_index=0,
        target_text=original_text,
        replacement_text=replacement_text,
        operator_sequence=[record],
        alignment=alignment,
    )

    assert plan is not None
    match_segments = [segment for segment in plan.segments if segment.role == "match"]
    assert len(match_segments) == 1
    segment = match_segments[0]

    assert segment.planned_replacement == replacement_text
    assert segment.replacement_start == 0
    assert segment.replacement_end == len(replacement_text)
    assert segment.slice_max_extents
    assert segment.slice_max_extents[0] == (0, len(original_text))
    assert segment.operator_fragments
    fragment_entry = segment.operator_fragments[0]
    assert fragment_entry.get("type") == "string"
    assert fragment_entry.get("text") == original_text


def test_build_replacement_plan_handles_leading_operator_whitespace():
    target_text = "worst-case"
    replacement_text = "best-case"

    span = SpanRecord(
        page_index=0,
        block_index=0,
        line_index=0,
        span_index=0,
        text=target_text,
        font="F1",
        font_size=9.0,
        bbox=(0.0, 0.0, 60.0, 12.0),
        origin=(0.0, 0.0),
        direction=(1.0, 0.0),
        matrix=(9.0, 0.0, 0.0, 9.0, 0.0, 0.0),
        ascent=0.0,
        descent=0.0,
        characters=[(ch, (idx * 5.0, 0.0, (idx + 1) * 5.0, 10.0)) for idx, ch in enumerate(target_text)],
        normalized_text=target_text,
        normalized_chars=[(ch, (idx * 5.0, 0.0, (idx + 1) * 5.0, 10.0)) for idx, ch in enumerate(target_text)],
        grapheme_slices=[(ch, idx, idx + 1) for idx, ch in enumerate(target_text)],
        normalized_to_raw_indices=[(idx, idx + 1) for idx in range(len(target_text))],
    )

    operator = OperatorRecord(
        index=0,
        operator=b"Tj",
        operands=(ByteStringObject(f" {target_text}".encode("latin-1")),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 5.0, 100.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 5.0, 100.0),
        font_resource="/F1",
        font_size=9.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=12.0,
        text_rise=0.0,
        text_fragments=[f" {target_text}"],
        text_adjustments=None,
        operand_types=["string:text"],
        literal_kind="text",
        raw_bytes=[f" {target_text}".encode("latin-1")],
        advance=None,
        post_text_matrix=(1.0, 0.0, 0.0, 1.0, 65.0, 100.0),
        advance_direction=None,
        advance_start_projection=None,
        advance_end_projection=None,
        advance_delta=None,
        advance_error=None,
        advance_warning=None,
        world_start=None,
        world_end=None,
        suffix_matrix_error=None,
    )

    alignment = {
        operator.index: [SpanSlice(span=span, span_start=0, span_end=len(target_text))]
    }

    plan = build_replacement_plan(
        page_index=0,
        target_text=target_text,
        replacement_text=replacement_text,
        operator_sequence=[operator],
        alignment=alignment,
    )

    assert plan is not None
    match_segments = [segment for segment in plan.segments if segment.role == "match"]
    assert match_segments, "Expected match segment despite leading whitespace"
    first_segment = match_segments[0]
    assert first_segment.span_slices
    slice_info = first_segment.span_slices[0]
    assert slice_info.span_start == 0
    assert slice_info.span_end == len(target_text)
