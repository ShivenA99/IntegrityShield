from __future__ import annotations

from typing import List, Optional

import pytest
from PyPDF2 import PdfWriter
from PyPDF2.generic import ArrayObject, ByteStringObject, FloatObject, NameObject, NumberObject, TextStringObject

from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer, TextRun
from app.services.pipeline.enhancement_methods.match_planner import ReplacementPlan, ReplacementSegment
from app.services.pipeline.enhancement_methods.content_state_tracker import OperatorRecord
from app.services.pipeline.enhancement_methods.span_alignment import SpanSlice


def _build_replacement_segment(
    operator_index: int,
    role: str,
    text: str,
    matrix: tuple[float, float, float, float, float, float],
    literal_kind: Optional[str] = None,
    requires_isolation: bool = False,
) -> ReplacementSegment:
    return ReplacementSegment(
        operator_index=operator_index,
        role=role,
        text=text,
        local_start=0,
        local_end=len(text),
        span_slices=[],
        matrix=matrix,
        font_resource="/F1",
        font_size=12.0,
        width=float(len(text) * 5),
        target_start=None,
        target_end=None,
        literal_kind=literal_kind,
        requires_isolation=requires_isolation,
    )


def test_merge_runs_respects_existing_text_state():
    renderer = BaseRenderer()

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([
            FloatObject(1.0),
            FloatObject(0.0),
            FloatObject(0.0),
            FloatObject(1.0),
            FloatObject(50.0),
            FloatObject(700.0),
        ], b"Tm"),
        ([TextStringObject("Hello world")], b"Tj"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="Hello world",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        width=60.0,
        source_index=3,
    )

    prefix_segment = _build_replacement_segment(
        operator_index=3,
        role="prefix",
        text="Hello ",
        matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
    )
    match_segment = _build_replacement_segment(
        operator_index=3,
        role="match",
        text="Universe",
        matrix=(1.0, 0.0, 0.0, 1.0, 82.0, 700.0),
    )

    prefix_run = TextRun(
        page_index=0,
        order=0,
        text="Hello ",
        font="/F1",
        fontsize=12.0,
        matrix=prefix_segment.matrix,
        width=30.0,
        source_index=3,
        is_modified=True,
        rewrite_context={"segment": "prefix"},
        plan_segment=prefix_segment,
    )

    match_run = TextRun(
        page_index=0,
        order=1,
        text="Universe",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=40.0,
        source_index=3,
        is_modified=True,
        rewrite_context={"segment": "match"},
        plan_segment=match_segment,
    )

    operator_record = OperatorRecord(
        index=3,
        operator=b"Tj",
        operands=(TextStringObject("Hello world"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["Hello world"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"Hello world"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [prefix_run, match_run],
        {3},
        {3: operator_record},
    )

    tf_count = sum(1 for _, operator in merged if operator == b"Tf")
    assert tf_count == 1, "Merge should not emit redundant Tf operators"

    replacement_texts = [
        str(operands[0])
        for operands, operator in merged
        if operator == b"Tj"
    ]
    assert replacement_texts == ["Hello Universe"], "Expected inline replacement"

    assert merged[0][1] == b"BT"
    assert merged[-1][1] == b"ET"


def test_merge_runs_without_plan_uses_run_defaults():
    renderer = BaseRenderer()

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([
            FloatObject(1.0),
            FloatObject(0.0),
            FloatObject(0.0),
            FloatObject(1.0),
            FloatObject(20.0),
            FloatObject(400.0),
        ], b"Tm"),
        ([TextStringObject("Sample")], b"Tj"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="Sample",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 20.0, 400.0),
        width=30.0,
        source_index=3,
    )

    updated_run = TextRun(
        page_index=0,
        order=0,
        text="Example",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 20.0, 400.0),
        width=30.0,
        source_index=3,
        is_modified=True,
    )

    operator_record = OperatorRecord(
        index=3,
        operator=b"Tj",
        operands=(TextStringObject("Sample"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 20.0, 400.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 20.0, 400.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["Sample"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"Sample"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [updated_run],
        {3},
        {3: operator_record},
    )

    tf_count = sum(1 for _, operator in merged if operator == b"Tf")
    assert tf_count == 1

    tm_operands = [operands for operands, operator in merged if operator == b"Tm"]
    expected_tm = [
        FloatObject(1.0),
        FloatObject(0.0),
        FloatObject(0.0),
        FloatObject(1.0),
        FloatObject(20.0),
        FloatObject(400.0),
    ]
    assert tm_operands and all(ops == expected_tm for ops in tm_operands)

    texts = [str(operands[0]) for operands, operator in merged if operator == b"Tj"]
    assert texts == ["Example"]


def test_ensure_font_resource_injects_missing_font():
    renderer = BaseRenderer()
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)

    resources_before = page.get(NameObject("/Resources"))
    assert resources_before is None or NameObject("/Font") not in resources_before

    renderer._ensure_font_resource(page, writer, "/Courier")

    resources = page.get(NameObject("/Resources"))
    assert resources is not None

    fonts = resources.get(NameObject("/Font"))
    assert fonts is not None
    if hasattr(fonts, "get_object"):
        fonts = fonts.get_object()

    assert NameObject("/Courier") in fonts


def test_inline_tj_single_match_rewrite():
    renderer = BaseRenderer()

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([TextStringObject("Foo")], b"Tj"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="Foo",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 15.0, 100.0),
        width=30.0,
        source_index=2,
    )

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="Bar",
        matrix=(1.0, 0.0, 0.0, 1.0, 15.0, 100.0),
    )
    match_segment.width = 30.0

    replacement_run = TextRun(
        page_index=0,
        order=0,
        text="Bar",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=30.0,
        source_index=2,
        is_modified=True,
        plan_segment=match_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"Tj",
        operands=(TextStringObject("Foo"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 15.0, 100.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 15.0, 100.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["Foo"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"Foo"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [replacement_run],
        {2},
        {2: operator_record},
    )

    assert merged[2][1] == b"Tj"
    assert str(merged[2][0][0]) == "Bar"
    assert merged == [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([TextStringObject("Bar")], b"Tj"),
        ([], b"ET"),
    ]


def test_isolation_emits_bt_blocks_when_width_mismatch():
    renderer = BaseRenderer()

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([
            FloatObject(1.0),
            FloatObject(0.0),
            FloatObject(0.0),
            FloatObject(1.0),
            FloatObject(50.0),
            FloatObject(700.0),
        ], b"Tm"),
        ([TextStringObject("Hello world")], b"Tj"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="Hello world",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        width=60.0,
        source_index=3,
    )

    prefix_segment = _build_replacement_segment(
        operator_index=3,
        role="prefix",
        text="Hello ",
        matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
    )
    match_segment = _build_replacement_segment(
        operator_index=3,
        role="match",
        text="Universe",
        matrix=(1.0, 0.0, 0.0, 1.0, 82.0, 700.0),
    )
    match_segment.width = 120.0  # Force width mismatch to trigger isolation
    suffix_segment = _build_replacement_segment(
        operator_index=3,
        role="suffix",
        text="",  # no suffix text
        matrix=(1.0, 0.0, 0.0, 1.0, 82.0, 700.0),
    )

    prefix_run = TextRun(
        page_index=0,
        order=0,
        text="Hello ",
        font="/F1",
        fontsize=12.0,
        matrix=prefix_segment.matrix,
        width=30.0,
        source_index=3,
        is_modified=True,
        plan_segment=prefix_segment,
    )

    match_run = TextRun(
        page_index=0,
        order=1,
        text="Universe",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=40.0,
        source_index=3,
        is_modified=True,
        plan_segment=match_segment,
    )

    replacement_runs = [prefix_run, match_run]

    operator_record = OperatorRecord(
        index=3,
        operator=b"Tj",
        operands=(TextStringObject("Hello world"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["Hello world"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"Hello world"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        replacement_runs,
        {3},
        {3: operator_record},
    )

    ops = [op for _, op in merged]
    assert ops.count(b"ET") >= 2 and ops.count(b"BT") >= 2, "Expected isolation ET/BT blocks"
    assert any(op == b"Tj" and str(operands[0]) == "Universe" for operands, op in merged)


def test_isolation_restores_state_with_planner_metadata():
    renderer = BaseRenderer()

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([
            FloatObject(1.0),
            FloatObject(0.0),
            FloatObject(0.0),
            FloatObject(1.0),
            FloatObject(50.0),
            FloatObject(700.0),
        ], b"Tm"),
        ([TextStringObject("Hello world")], b"Tj"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="Hello world",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        char_spacing=0.4,
        word_spacing=1.2,
        horizontal_scaling=110.0,
        text_rise=2.3,
        width=60.0,
        source_index=3,
    )

    prefix_segment = _build_replacement_segment(
        operator_index=3,
        role="prefix",
        text="Hello ",
        matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
    )

    match_segment = _build_replacement_segment(
        operator_index=3,
        role="match",
        text="Universe",
        matrix=(1.0, 0.0, 0.0, 1.0, 90.0, 705.0),
    )
    match_segment.width = 120.0

    prefix_run = TextRun(
        page_index=0,
        order=0,
        text="Hello ",
        font="/F1",
        fontsize=12.0,
        matrix=prefix_segment.matrix,
        char_spacing=0.4,
        word_spacing=1.2,
        horizontal_scaling=110.0,
        text_rise=2.3,
        width=30.0,
        source_index=3,
        is_modified=True,
        plan_segment=prefix_segment,
    )

    match_run = TextRun(
        page_index=0,
        order=1,
        text="Universe",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        char_spacing=0.8,
        word_spacing=1.7,
        horizontal_scaling=95.0,
        text_rise=1.1,
        width=40.0,
        source_index=3,
        is_modified=True,
        plan_segment=match_segment,
    )

    replacement_runs = [prefix_run, match_run]

    operator_record = OperatorRecord(
        index=3,
        operator=b"Tj",
        operands=(TextStringObject("Hello world"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 700.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.4,
        word_spacing=1.2,
        horizontal_scaling=110.0,
        leading=14.0,
        text_rise=2.3,
        text_fragments=["Hello world"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"Hello world"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        replacement_runs,
        {3},
        {3: operator_record},
    )

    # Locate isolated replacement block
    match_index = next(
        idx
        for idx, (operands, operator) in enumerate(merged)
        if operator == b"Tj" and str(operands[0]) == "Universe"
    )

    iso_bt_index = next(
        idx
        for idx in range(match_index, -1, -1)
        if merged[idx][1] == b"BT" and idx > 0 and merged[idx - 1][1] == b"ET"
    )

    isolated_block = merged[iso_bt_index:match_index]

    def find_op(block, target):
        for operands, operator in block:
            if operator == target and operands:
                try:
                    return float(operands[0])
                except (TypeError, ValueError):
                    return None
        return None

    assert find_op(isolated_block, b"Tc") == pytest.approx(0.8)
    assert find_op(isolated_block, b"Tw") == pytest.approx(1.7)
    assert find_op(isolated_block, b"Tz") == pytest.approx(95.0)
    assert find_op(isolated_block, b"Ts") == pytest.approx(1.1)

    reopen_bt_index = next(
        idx
        for idx in range(match_index + 1, len(merged))
        if merged[idx][1] == b"BT" and merged[idx - 1][1] == b"ET"
    )

    restored_block = merged[reopen_bt_index:]

    assert find_op(restored_block, b"Tc") == pytest.approx(0.4)
    assert find_op(restored_block, b"Tw") == pytest.approx(1.2)
    assert find_op(restored_block, b"Tz") == pytest.approx(110.0)
    assert find_op(restored_block, b"Ts") == pytest.approx(2.3)

    tm_operands = next(
        operands
        for operands, operator in restored_block
        if operator == b"Tm"
    )
    assert [float(item) for item in tm_operands] == [1.0, 0.0, 0.0, 1.0, 50.0, 700.0]


def test_cross_operator_replacement_uses_isolation_and_preserves_sequence():
    renderer = BaseRenderer()

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([
            FloatObject(1.0),
            FloatObject(0.0),
            FloatObject(0.0),
            FloatObject(1.0),
            FloatObject(10.0),
            FloatObject(700.0),
        ], b"Tm"),
        ([TextStringObject("Hello")], b"Tj"),
        ([TextStringObject("World")], b"Tj"),
        ([], b"ET"),
    ]

    first_run = TextRun(
        page_index=0,
        order=0,
        text="Hello",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 700.0),
        width=50.0,
        source_index=3,
    )

    second_run = TextRun(
        page_index=0,
        order=1,
        text="World",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 700.0),
        width=50.0,
        source_index=4,
    )

    prefix_seg = _build_replacement_segment(
        operator_index=3,
        role="prefix",
        text="Hel",
        matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 700.0),
    )
    prefix_seg.local_start = 0
    prefix_seg.local_end = 3
    prefix_seg.width = 30.0

    match_seg_first = _build_replacement_segment(
        operator_index=3,
        role="match",
        text="lo",
        matrix=(1.0, 0.0, 0.0, 1.0, 40.0, 700.0),
    )
    match_seg_first.local_start = 3
    match_seg_first.local_end = 5
    match_seg_first.target_start = 0
    match_seg_first.target_end = 2
    match_seg_first.width = 75.0  # force width mismatch

    match_seg_second = _build_replacement_segment(
        operator_index=4,
        role="match",
        text="Wo",
        matrix=(1.0, 0.0, 0.0, 1.0, 65.0, 700.0),
    )
    match_seg_second.local_start = 0
    match_seg_second.local_end = 2
    match_seg_second.target_start = 2
    match_seg_second.target_end = 5
    match_seg_second.width = 80.0

    suffix_seg_second = _build_replacement_segment(
        operator_index=4,
        role="suffix",
        text="rld",
        matrix=(1.0, 0.0, 0.0, 1.0, 90.0, 700.0),
    )
    suffix_seg_second.local_start = 2
    suffix_seg_second.local_end = 5
    suffix_seg_second.width = 30.0

    plan = ReplacementPlan(
        page_index=0,
        original_text="loWo",
        replacement_text="Space",
        segments=[
            prefix_seg,
            match_seg_first,
            match_seg_second,
            suffix_seg_second,
        ],
    )

    replacement = {
        "context": {"matched_text": "loWo"},
        "replacement": "Space",
        "_replacement_plan": plan,
    }

    updated_runs, modified_sources, _ = renderer._apply_replacements_to_runs(
        [first_run, second_run],
        [replacement],
        doc_page=object(),
        run_id=None,
    )

    operator_record_first = OperatorRecord(
        index=3,
        operator=b"Tj",
        operands=(TextStringObject("Hello"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 700.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 700.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["Hello"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"Hello"],
    )

    operator_record_second = OperatorRecord(
        index=4,
        operator=b"Tj",
        operands=(TextStringObject("World"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 700.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 700.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["World"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"World"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [first_run, second_run],
        updated_runs,
        modified_sources,
        {3: operator_record_first, 4: operator_record_second},
    )

    extracted_text = [
        str(operands[0])
        for operands, operator in merged
        if operator == b"Tj" and operands
    ]

    assert extracted_text == ["Hel", "Sp", "ace", "rld"]

    ops = [operator for _, operator in merged]
    assert ops.count(b"BT") >= 3
    assert ops.count(b"ET") >= 3


def test_cross_operator_deletion_removes_segments_and_restores_suffix():
    renderer = BaseRenderer()

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([
            FloatObject(1.0),
            FloatObject(0.0),
            FloatObject(0.0),
            FloatObject(1.0),
            FloatObject(10.0),
            FloatObject(700.0),
        ], b"Tm"),
        ([TextStringObject("Hello")], b"Tj"),
        ([TextStringObject("World")], b"Tj"),
        ([], b"ET"),
    ]

    first_run = TextRun(
        page_index=0,
        order=0,
        text="Hello",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 700.0),
        width=50.0,
        source_index=3,
    )

    second_run = TextRun(
        page_index=0,
        order=1,
        text="World",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 700.0),
        width=50.0,
        source_index=4,
    )

    prefix_seg = _build_replacement_segment(
        operator_index=3,
        role="prefix",
        text="Hel",
        matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 700.0),
    )
    prefix_seg.local_start = 0
    prefix_seg.local_end = 3
    prefix_seg.width = 30.0

    match_seg_first = _build_replacement_segment(
        operator_index=3,
        role="match",
        text="lo",
        matrix=(1.0, 0.0, 0.0, 1.0, 40.0, 700.0),
    )
    match_seg_first.local_start = 3
    match_seg_first.local_end = 5
    match_seg_first.target_start = 0
    match_seg_first.target_end = 0
    match_seg_first.width = 20.0

    match_seg_second = _build_replacement_segment(
        operator_index=4,
        role="match",
        text="Wo",
        matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 700.0),
    )
    match_seg_second.local_start = 0
    match_seg_second.local_end = 2
    match_seg_second.target_start = 0
    match_seg_second.target_end = 0
    match_seg_second.width = 25.0

    suffix_seg_second = _build_replacement_segment(
        operator_index=4,
        role="suffix",
        text="rld",
        matrix=(1.0, 0.0, 0.0, 1.0, 85.0, 700.0),
    )
    suffix_seg_second.local_start = 2
    suffix_seg_second.local_end = 5
    suffix_seg_second.width = 30.0

    plan = ReplacementPlan(
        page_index=0,
        original_text="loWo",
        replacement_text="",
        segments=[
            prefix_seg,
            match_seg_first,
            match_seg_second,
            suffix_seg_second,
        ],
    )

    replacement = {
        "context": {"matched_text": "loWo"},
        "replacement": "",
        "_replacement_plan": plan,
    }

    updated_runs, modified_sources, _ = renderer._apply_replacements_to_runs(
        [first_run, second_run],
        [replacement],
        doc_page=object(),
        run_id=None,
    )

    operator_record_first = OperatorRecord(
        index=3,
        operator=b"Tj",
        operands=(TextStringObject("Hello"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 700.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 700.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["Hello"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"Hello"],
    )

    operator_record_second = OperatorRecord(
        index=4,
        operator=b"Tj",
        operands=(TextStringObject("World"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 700.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 700.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["World"],
        text_adjustments=None,
        operand_types=["string"],
        literal_kind="text",
        raw_bytes=[b"World"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [first_run, second_run],
        updated_runs,
        modified_sources,
        {3: operator_record_first, 4: operator_record_second},
    )

    extracted_text = [
        str(operands[0])
        for operands, operator in merged
        if operator == b"Tj" and operands
    ]

    assert extracted_text == ["Hel", "rld"]


def test_tj_deletion_forces_isolation_when_segment_requests_it():
    renderer = BaseRenderer()

    array = ArrayObject([
        TextStringObject("prefix"),
        NumberObject(-40),
        TextStringObject("match"),
        NumberObject(-20),
        TextStringObject("suffix"),
    ])

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([array], b"TJ"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="prefixmatchsuffix",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=85.0,
        source_index=2,
    )

    prefix_segment = _build_replacement_segment(
        operator_index=2,
        role="prefix",
        text="prefix",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        literal_kind="array",
    )
    prefix_segment.local_start = 0
    prefix_segment.local_end = len("prefix")

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="match",
        matrix=(1.0, 0.0, 0.0, 1.0, 30.0, 0.0),
        literal_kind="array",
        requires_isolation=True,
    )
    match_segment.local_start = len("prefix")
    match_segment.local_end = len("prefixmatch")
    match_segment.target_start = 0
    match_segment.target_end = 0

    suffix_segment = _build_replacement_segment(
        operator_index=2,
        role="suffix",
        text="suffix",
        matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 0.0),
        literal_kind="array",
    )
    suffix_segment.local_start = len("prefixmatch")
    suffix_segment.local_end = len("prefixmatchsuffix")

    plan = ReplacementPlan(
        page_index=0,
        original_text="match",
        replacement_text="",
        segments=[prefix_segment, match_segment, suffix_segment],
    )

    replacement = {
        "context": {"matched_text": "match"},
        "replacement": "",
        "_replacement_plan": plan,
    }

    updated_runs, modified_sources, _ = renderer._apply_replacements_to_runs(
        [original_run],
        [replacement],
        doc_page=object(),
        run_id=None,
    )

    match_runs = [run for run in updated_runs if run.plan_segment and run.plan_segment.role == "match"]
    assert match_runs, "Expected match run placeholder"
    match_run = match_runs[0]
    assert match_run.text == ""
    assert match_run.plan_segment.requires_isolation is True
    assert match_run.rewrite_context.get("empty_replacement") is True

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["prefix", "match", "suffix"],
        text_adjustments=None,
        operand_types=["string", "number", "string", "number", "string"],
        literal_kind="array",
        raw_bytes=[b"prefix", b"match", b"suffix"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        updated_runs,
        modified_sources,
        {2: operator_record},
    )

    collected_parts: List[str] = []
    suffix_arrays: List[ArrayObject] = []

    for operands, operator in merged:
        if operator == b"Tj":
            for obj in operands:
                if isinstance(obj, TextStringObject):
                    collected_parts.append(str(obj))
        elif operator == b"TJ" and operands:
            array_operand = operands[0]
            if not isinstance(array_operand, ArrayObject):
                continue
            text_values = [
                str(entry)
                for entry in array_operand
                if isinstance(entry, TextStringObject)
            ]
            combined = "".join(text_values)
            assert "match" not in combined
            collected_parts.append(combined)
            suffix_arrays.append(array_operand)

    assert suffix_arrays, "Expected isolation suffix array"
    assert "".join(collected_parts) == "prefixsuffix"

    bt_et_ops = [op for _, op in merged if op in {b"BT", b"ET"}]
    assert bt_et_ops.count(b"BT") >= 2
    assert bt_et_ops.count(b"ET") >= 2


def test_tj_array_inline_rewrite_rejects_disjoint_match_segments():
    renderer = BaseRenderer()

    array = ArrayObject([
        TextStringObject("AB"),
        NumberObject(-20),
        TextStringObject("CD"),
    ])

    original_run = TextRun(
        page_index=0,
        order=0,
        text="ABCD",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=80.0,
        source_index=2,
    )

    first_match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="A",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    first_match_segment.local_start = 0
    first_match_segment.local_end = 1
    first_match_segment.target_start = 0
    first_match_segment.target_end = 1

    second_match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="D",
        matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 0.0),
    )
    second_match_segment.local_start = 3
    second_match_segment.local_end = 4
    second_match_segment.target_start = 1
    second_match_segment.target_end = 2

    first_run = TextRun(
        page_index=0,
        order=0,
        text="X",
        font="/F1",
        fontsize=12.0,
        matrix=first_match_segment.matrix,
        width=10.0,
        source_index=2,
        is_modified=True,
        plan_segment=first_match_segment,
    )

    second_run = TextRun(
        page_index=0,
        order=1,
        text="Y",
        font="/F1",
        fontsize=12.0,
        matrix=second_match_segment.matrix,
        width=10.0,
        source_index=2,
        is_modified=True,
        plan_segment=second_match_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["AB", "CD"],
        text_adjustments=[-20.0],
        operand_types=["string", "number", "string"],
        literal_kind="array",
        raw_bytes=[b"AB", b"CD"],
    )

    result = renderer._rewrite_single_tj_array(
        [array],
        [first_run, second_run],
        operator_record,
        original_run,
    )

    assert result is None, "Disjoint match segments should force isolation fallback"


def test_tj_array_inline_rewrite_pads_width_with_kerning():
    renderer = BaseRenderer()

    array = ArrayObject([
        TextStringObject("prefix"),
        TextStringObject("LSTM"),
        TextStringObject("suffix"),
    ])

    original_run = TextRun(
        page_index=0,
        order=0,
        text="prefixLSTMsuffix",
        font="/F1",
        fontsize=10.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=80.0,
        source_index=2,
        horizontal_scaling=100.0,
    )

    prefix_segment = _build_replacement_segment(
        operator_index=2,
        role="prefix",
        text="prefix",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    prefix_segment.local_start = 0
    prefix_segment.local_end = len("prefix")

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="LSTM",
        matrix=(1.0, 0.0, 0.0, 1.0, 30.0, 0.0),
    )
    match_segment.local_start = len("prefix")
    match_segment.local_end = len("prefix") + len("LSTM")
    match_segment.width = 40.0

    suffix_segment = _build_replacement_segment(
        operator_index=2,
        role="suffix",
        text="suffix",
        matrix=(1.0, 0.0, 0.0, 1.0, 70.0, 0.0),
    )
    suffix_segment.local_start = len("prefixLSTM")
    suffix_segment.local_end = len("prefixLSTMsuffix")

    prefix_run = TextRun(
        page_index=0,
        order=0,
        text="prefix",
        font="/F1",
        fontsize=10.0,
        matrix=prefix_segment.matrix,
        width=30.0,
        source_index=2,
        is_modified=True,
        plan_segment=prefix_segment,
    )

    match_run = TextRun(
        page_index=0,
        order=1,
        text="RNN",
        font="/F1",
        fontsize=10.0,
        matrix=match_segment.matrix,
        width=40.0,
        source_index=2,
        is_modified=True,
        plan_segment=match_segment,
        rewrite_context={
            "replacement_measured_width": 30.0,
            "original_segment_width": 40.0,
            "font_size": 10.0,
            "horizontal_scaling": 100.0,
        },
    )

    suffix_run = TextRun(
        page_index=0,
        order=2,
        text="suffix",
        font="/F1",
        fontsize=10.0,
        matrix=suffix_segment.matrix,
        width=20.0,
        source_index=2,
        is_modified=True,
        plan_segment=suffix_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=10.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=12.0,
        text_rise=0.0,
        text_fragments=["prefix", "LSTM", "suffix"],
        operand_types=["string", "string", "string"],
        literal_kind="array",
        raw_bytes=[b"prefix", b"LSTM", b"suffix"],
    )

    result = renderer._rewrite_single_tj_array(
        [array],
        [prefix_run, match_run, suffix_run],
        operator_record,
        original_run,
    )

    assert result, "Expected inline TJ rewrite"
    rewritten_array = result[0][0][0]

    assert isinstance(rewritten_array, ArrayObject)
    elements = list(rewritten_array)
    kern_values = [float(elem) for elem in elements if isinstance(elem, FloatObject)]
    assert kern_values and pytest.approx(kern_values[0], rel=1e-6) == -1000.0

    rebuilt_text = "".join(
        elem.decode("latin-1") if isinstance(elem, ByteStringObject) else str(elem)
        for elem in elements
        if isinstance(elem, (TextStringObject, ByteStringObject))
    )
    assert rebuilt_text == "prefixRNNsuffix"


def test_isolation_preserves_byte_literals_when_width_mismatch():
    renderer = BaseRenderer()

    array = ArrayObject([
        TextStringObject("prefix"),
        ByteStringObject(b"\x01\x02"),
        NumberObject(-40),
        TextStringObject("suffix"),
    ])

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([array], b"TJ"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="prefix\x01\x02suffix",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=60.0,
        source_index=2,
    )

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="\x01\x02",
        matrix=(1.0, 0.0, 0.0, 1.0, 30.0, 0.0),
        literal_kind="byte",
    )
    match_segment.local_start = len("prefix")
    match_segment.local_end = len("prefix") + 2
    match_segment.width = 8.0

    replacement_run = TextRun(
        page_index=0,
        order=1,
        text="CC",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=12.0,  # force width mismatch → isolation
        source_index=2,
        is_modified=True,
        plan_segment=match_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["prefix", "\x01\x02", "suffix"],
        text_adjustments=[-40.0],
        operand_types=["string:text", "number", "string:byte", "number", "string:text"],
        literal_kind="array",
        raw_bytes=[b"prefix", b"\x01\x02", b"suffix"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [replacement_run],
        {2},
        {2: operator_record},
    )

    isolated_arrays = [
        operands[0]
        for operands, operator in merged
        if operator == b"TJ" and operands and isinstance(operands[0], ArrayObject)
    ]
    assert isolated_arrays, "Expected isolation to emit TJ array"

    byte_segments = [
        bytes(entry)
        for array in isolated_arrays
        for entry in array
        if isinstance(entry, ByteStringObject)
    ]
    assert byte_segments and byte_segments[0] == b"CC"

    ops = [operator for _, operator in merged]
    assert ops.count(b"BT") >= 2
    assert ops.count(b"ET") >= 2


def test_isolation_tj_preserves_internal_kern_adjustments():
    renderer = BaseRenderer()

    array = ArrayObject(
        [
            TextStringObject("C"),
            NumberObject(-75),
            TextStringObject("N"),
            NumberObject(-30),
            TextStringObject("N"),
            NumberObject(-20),
            TextStringObject("s"),
        ]
    )

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([array], b"TJ"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="CNNs",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=50.0,
        source_index=2,
    )

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="NNs",
        matrix=(1.0, 0.0, 0.0, 1.0, 20.0, 0.0),
    )
    match_segment.local_start = 1
    match_segment.local_end = 4
    match_segment.width = 120.0
    match_segment.requires_isolation = True

    replacement_run = TextRun(
        page_index=0,
        order=1,
        text="RNNs",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=80.0,
        source_index=2,
        is_modified=True,
        plan_segment=match_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["C", "N", "N", "s"],
        text_adjustments=[-75.0, -30.0, -20.0],
        operand_types=[
            "string:text",
            "number",
            "string:text",
            "number",
            "string:text",
            "number",
            "string:text",
        ],
        literal_kind="array",
        raw_bytes=[b"C", b"N", b"N", b"s"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [replacement_run],
        {2},
        {2: operator_record},
    )

    isolated_arrays = [
        operands[0]
        for operands, operator in merged
        if operator == b"TJ" and operands and isinstance(operands[0], ArrayObject)
    ]
    assert isolated_arrays, "Expected isolated TJ output"

    target_array = next(
        (
            array
            for array in isolated_arrays
            if any(isinstance(entry, TextStringObject) and str(entry).startswith("R") for entry in array)
        ),
        None,
    )
    assert target_array is not None, "Replacement TJ array not found"

    kern_values = [float(entry) for entry in target_array if isinstance(entry, FloatObject)]
    assert kern_values == [-30.0, -20.0]

    text_values = [str(entry) for entry in target_array if isinstance(entry, TextStringObject)]
    assert text_values == ["R", "N", "Ns"]


def test_isolation_prefix_tj_reuses_original_kern_values():
    renderer = BaseRenderer()

    array = ArrayObject(
        [
            TextStringObject("C"),
            NumberObject(-75),
            TextStringObject("N"),
            NumberObject(-30),
            TextStringObject("N"),
            NumberObject(-20),
            TextStringObject("s"),
        ]
    )

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([array], b"TJ"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="CNNs",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=42.0,
        source_index=2,
    )

    prefix_segment = _build_replacement_segment(
        operator_index=2,
        role="prefix",
        text="CNN",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    prefix_segment.local_start = 0
    prefix_segment.local_end = 3

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="s",
        matrix=(1.0, 0.0, 0.0, 1.0, 32.0, 0.0),
    )
    match_segment.local_start = 3
    match_segment.local_end = 4
    match_segment.width = 25.0  # force isolation via width mismatch

    prefix_run = TextRun(
        page_index=0,
        order=0,
        text="CNN",
        font="/F1",
        fontsize=12.0,
        matrix=prefix_segment.matrix,
        width=30.0,
        source_index=2,
        is_modified=True,
        plan_segment=prefix_segment,
    )

    match_run = TextRun(
        page_index=0,
        order=1,
        text="Z",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=10.0,
        source_index=2,
        is_modified=True,
        plan_segment=match_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["C", "N", "N", "s"],
        text_adjustments=[-75.0, -30.0, -20.0],
        operand_types=[
            "string:text",
            "number",
            "string:text",
            "number",
            "string:text",
            "number",
            "string:text",
        ],
        literal_kind="array",
        raw_bytes=[b"C", b"N", b"N", b"s"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [prefix_run, match_run],
        {2},
        {2: operator_record},
    )

    tj_arrays = [
        operands[0]
        for operands, operator in merged
        if operator == b"TJ" and operands and isinstance(operands[0], ArrayObject)
    ]

    assert tj_arrays, "Prefix rewrite should emit TJ array"

    prefix_entries = tj_arrays[0]
    prefix_floats = [float(entry) for entry in prefix_entries if isinstance(entry, FloatObject)]
    prefix_strings = [str(entry) for entry in prefix_entries if isinstance(entry, TextStringObject)]

    assert prefix_floats == [-75.0, -30.0]
    assert prefix_strings == ["C", "N", "N"]


def test_isolation_suffix_tj_preserves_trailing_kern_values():
    renderer = BaseRenderer()

    array = ArrayObject(
        [
            TextStringObject("C"),
            NumberObject(-75),
            TextStringObject("N"),
            NumberObject(-30),
            TextStringObject("N"),
            NumberObject(-20),
            TextStringObject("s"),
        ]
    )

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([array], b"TJ"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="CNNs",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=42.0,
        source_index=2,
    )

    prefix_segment = _build_replacement_segment(
        operator_index=2,
        role="prefix",
        text="CN",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    prefix_segment.local_start = 0
    prefix_segment.local_end = 2

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="N",
        matrix=(1.0, 0.0, 0.0, 1.0, 25.0, 0.0),
        requires_isolation=True,
    )
    match_segment.local_start = 2
    match_segment.local_end = 3
    match_segment.width = 50.0

    suffix_segment = _build_replacement_segment(
        operator_index=2,
        role="suffix",
        text="s",
        matrix=(1.0, 0.0, 0.0, 1.0, 35.0, 0.0),
    )
    suffix_segment.local_start = 3
    suffix_segment.local_end = 4

    prefix_run = TextRun(
        page_index=0,
        order=0,
        text="CN",
        font="/F1",
        fontsize=12.0,
        matrix=prefix_segment.matrix,
        width=28.0,
        source_index=2,
        is_modified=True,
        plan_segment=prefix_segment,
    )

    match_run = TextRun(
        page_index=0,
        order=1,
        text="Z",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=12.0,
        source_index=2,
        is_modified=True,
        plan_segment=match_segment,
    )

    suffix_run = TextRun(
        page_index=0,
        order=2,
        text="s",
        font="/F1",
        fontsize=12.0,
        matrix=suffix_segment.matrix,
        width=10.0,
        source_index=2,
        is_modified=True,
        plan_segment=suffix_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["C", "N", "N", "s"],
        text_adjustments=[-75.0, -30.0, -20.0],
        operand_types=[
            "string:text",
            "number",
            "string:text",
            "number",
            "string:text",
            "number",
            "string:text",
        ],
        literal_kind="array",
        raw_bytes=[b"C", b"N", b"N", b"s"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [prefix_run, match_run, suffix_run],
        {2},
        {2: operator_record},
    )

    suffix_arrays = []
    for operands, operator in merged:
        if operator != b"TJ" or not operands:
            continue
        array_operand = operands[0]
        if not isinstance(array_operand, ArrayObject):
            continue
        text_values = [
            str(entry)
            for entry in array_operand
            if isinstance(entry, TextStringObject)
        ]
        if text_values == ["s"]:
            suffix_arrays.append(array_operand)

    assert suffix_arrays, "Expected isolated suffix TJ array"

    suffix_floats = [
        float(entry)
        for entry in suffix_arrays[0]
        if isinstance(entry, FloatObject)
    ]
    assert suffix_floats == [-20.0]


def test_emit_run_operations_uses_bytestring_for_byte_literal_tj():
    renderer = BaseRenderer()

    segment = _build_replacement_segment(
        operator_index=5,
        role="match",
        text="\x01\x02",
        matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 20.0),
        literal_kind="byte",
    )

    run = TextRun(
        page_index=0,
        order=0,
        text="\x01\x02",
        font="/F1",
        fontsize=12.0,
        matrix=segment.matrix,
        source_index=5,
        plan_segment=segment,
        is_modified=True,
    )

    record = OperatorRecord(
        index=5,
        operator=b"Tj",
        operands=(ByteStringObject(b"\x01\x02"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=segment.matrix,
        text_line_matrix=segment.matrix,
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["\x01\x02"],
        text_adjustments=None,
        operand_types=["string:byte"],
        literal_kind="byte",
        raw_bytes=[b"\x01\x02"],
    )

    operations: List[Tuple[List[object], bytes]] = []
    state: Dict[str, Optional[float | str]] = {
        "font": None,
        "size": None,
        "char_spacing": 0.0,
        "word_spacing": 0.0,
        "horizontal_scaling": 100.0,
        "text_rise": 0.0,
    }

    renderer._emit_run_operations(run, operations, state, record)

    tj_operands = [ops for ops, op in operations if op == b"Tj"]
    assert tj_operands, "Expected Tj emission"
    operand = tj_operands[-1][0]
    assert isinstance(operand, ByteStringObject)
    assert bytes(operand) == b"\x01\x02"


def test_tj_byte_literal_isolation_emits_byte_string():
    renderer = BaseRenderer()

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([ByteStringObject(b"\x01\x02\x03")], b"Tj"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="\x01\x02\x03",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=30.0,
        source_index=2,
    )

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="\x01\x02\x03",
        matrix=original_run.matrix,
        literal_kind="byte",
    )
    match_segment.local_start = 0
    match_segment.local_end = len(original_run.text)
    match_segment.width = 20.0

    replacement_run = TextRun(
        page_index=0,
        order=0,
        text="CC",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=10.0,
        source_index=2,
        is_modified=True,
        plan_segment=match_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"Tj",
        operands=(ByteStringObject(b"\x01\x02\x03"),),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=original_run.matrix,
        text_line_matrix=original_run.matrix,
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["\x01\x02\x03"],
        text_adjustments=None,
        operand_types=["string:byte"],
        literal_kind="byte",
        raw_bytes=[b"\x01\x02\x03"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [replacement_run],
        {2},
        {2: operator_record},
    )

    isolated_bytes = [
        bytes(operands[0])
        for operands, operator in merged
        if operator == b"Tj" and operands and isinstance(operands[0], ByteStringObject)
    ]
    assert isolated_bytes[0] == b"CC"

    ops = [operator for _, operator in merged]
    assert ops.count(b"BT") >= 2
    assert ops.count(b"ET") >= 2
def test_measure_run_substring_width_falls_back_to_cached_width():
    renderer = BaseRenderer()

    run = TextRun(
        page_index=0,
        order=0,
        text="abcdef",
        font="/F1",
        fontsize=10.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=60.0,
        source_index=0,
    )

    class StubPage:
        def get_text_length(self, *_args, **_kwargs):
            raise RuntimeError("unavailable")

    stub_page = StubPage()

    substring = "abc"
    width = renderer._measure_run_substring_width(run, substring, stub_page)  # type: ignore[arg-type]

    assert width == pytest.approx(30.0)


def test_resolve_segment_width_respects_tolerance():
    renderer = BaseRenderer()
    segment = _build_replacement_segment(
        operator_index=0,
        role="prefix",
        text="abc",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )

    # Planned width matches fallback closely -> accept planner width
    segment.width = 12.2
    resolved = renderer._resolve_segment_width(segment, fallback_width=12.0, run_id=None, role="prefix")
    assert resolved == pytest.approx(12.2)

    # Large deviation -> fall back to measured width
    segment.width = 25.0
    resolved = renderer._resolve_segment_width(segment, fallback_width=12.0, run_id=None, role="prefix")
    assert resolved == pytest.approx(12.0)


def test_resolve_segment_width_uses_span_width_when_available():
    renderer = BaseRenderer()

    class DummySpan:
        def __init__(self) -> None:
            self.normalized_chars = [
                ("a", (0.0, 0.0, 3.0, 5.0)),
                ("b", (3.0, 0.0, 6.0, 5.0)),
                ("c", (6.0, 0.0, 9.0, 5.0)),
            ]
            self.characters = self.normalized_chars

    span = DummySpan()

    segment = _build_replacement_segment(
        operator_index=0,
        role="match",
        text="abc",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    segment.width = 50.0  # planner width far off
    segment.span_slices = [SpanSlice(span=span, span_start=0, span_end=3)]

    resolved = renderer._resolve_segment_width(segment, fallback_width=12.0, run_id=None, role="match")
    assert resolved == pytest.approx(9.0)


def test_apply_replacements_uses_resolved_width_for_suffix_translation():
    renderer = BaseRenderer()

    original_run = TextRun(
        page_index=0,
        order=0,
        text="XYZtail",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 20.0),
        width=70.0,
        source_index=5,
    )

    match_segment = ReplacementSegment(
        operator_index=5,
        role="match",
        text="XYZ",
        local_start=0,
        local_end=3,
        span_slices=[],
        matrix=(1.0, 0.0, 0.0, 1.0, 10.0, 20.0),
        font_resource="/F2",
        font_size=12.0,
        width=60.0,
        target_start=0,
        target_end=3,
    )

    plan = ReplacementPlan(
        page_index=0,
        original_text="XYZ",
        replacement_text="ABC",
        segments=[match_segment],
    )

    replacement = {
        "context": {"matched_text": "XYZ"},
        "replacement": "ABC",
        "_replacement_plan": plan,
    }

    updated_runs, _, _ = renderer._apply_replacements_to_runs(
        [original_run],
        [replacement],
        doc_page=object(),
        run_id=None,
    )

    match_runs = [run for run in updated_runs if run.text == "ABC"]
    suffix_runs = [run for run in updated_runs if run.text == "tail"]

    assert match_runs, "Expected replacement run"
    assert suffix_runs, "Expected suffix run"

    match_run = match_runs[0]
    suffix_run = suffix_runs[0]

    # fallback width should be based on original text proportion (3/7 of total width 70 = 30)
    assert match_run.width == pytest.approx(30.0)

    expected_suffix_x = original_run.matrix[4] + match_run.width
    assert suffix_run.matrix[4] == pytest.approx(expected_suffix_x)
def test_tj_array_inline_rewrite_preserves_kern_adjustments():
    renderer = BaseRenderer()

    array = ArrayObject([
        TextStringObject("prefix"),
        NumberObject(-40),
        TextStringObject("middle"),
        NumberObject(-20),
        TextStringObject("suffix"),
    ])

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([array], b"TJ"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="prefixmiddlesuffix",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=80.0,
        source_index=2,
    )

    prefix_segment = _build_replacement_segment(
        operator_index=2,
        role="prefix",
        text="prefix",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    prefix_segment.local_start = 0
    prefix_segment.local_end = len("prefix")

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="middle",
        matrix=(1.0, 0.0, 0.0, 1.0, 30.0, 0.0),
    )
    match_segment.local_start = len("prefix")
    match_segment.local_end = len("prefixmiddle")
    match_segment.width = 30.0

    suffix_segment = _build_replacement_segment(
        operator_index=2,
        role="suffix",
        text="suffix",
        matrix=(1.0, 0.0, 0.0, 1.0, 60.0, 0.0),
    )
    suffix_segment.local_start = len("prefixmiddle")
    suffix_segment.local_end = len("prefixmiddlesuffix")

    replacement_run = TextRun(
        page_index=0,
        order=1,
        text="centre",
        font="/F1",
        fontsize=12.0,
        matrix=match_segment.matrix,
        width=30.0,
        source_index=2,
        is_modified=True,
        plan_segment=match_segment,
    )

    prefix_run = TextRun(
        page_index=0,
        order=0,
        text="prefix",
        font="/F1",
        fontsize=12.0,
        matrix=prefix_segment.matrix,
        width=30.0,
        source_index=2,
        is_modified=True,
        plan_segment=prefix_segment,
    )

    suffix_run = TextRun(
        page_index=0,
        order=2,
        text="suffix",
        font="/F1",
        fontsize=12.0,
        matrix=suffix_segment.matrix,
        width=30.0,
        source_index=2,
        is_modified=True,
        plan_segment=suffix_segment,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["prefix", "middle", "suffix"],
        text_adjustments=None,
        operand_types=["string", "number", "string", "number", "string"],
        literal_kind="array",
        raw_bytes=[b"prefix", b"middle", b"suffix"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        [prefix_run, replacement_run, suffix_run],
        {2},
        {2: operator_record},
    )

    assert merged.count(([], b"BT")) == 1
    assert merged.count(([], b"ET")) == 1

    tj_arrays = [operands[0] for operands, operator in merged if operator == b"TJ"]
    assert len(tj_arrays) == 1

    result_array = tj_arrays[0]
    assert isinstance(result_array, ArrayObject)

    result_text = "".join(
        str(item)
        for item in result_array
        if isinstance(item, TextStringObject)
    )
    assert result_text == "prefixcentresuffix"

    kern_values = [
        float(item)
        for item in result_array
        if isinstance(item, (NumberObject, FloatObject))
    ]
    assert kern_values == [-40.0, -20.0]


def test_tj_array_inline_rewrite_preserves_byte_literal_segments():
    renderer = BaseRenderer()

    array = ArrayObject([
        TextStringObject("prefix"),
        ByteStringObject(b"\x01\x02"),
        NumberObject(-40),
        TextStringObject("suffix"),
    ])

    original_operations: List[tuple[List[object], bytes]] = [
        ([], b"BT"),
        ([NameObject("/F1"), FloatObject(12.0)], b"Tf"),
        ([array], b"TJ"),
        ([], b"ET"),
    ]

    original_run = TextRun(
        page_index=0,
        order=0,
        text="prefix\x01\x02suffix",
        font="/F1",
        fontsize=12.0,
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        width=60.0,
        source_index=2,
    )

    total_length = len(original_run.text)

    match_segment = _build_replacement_segment(
        operator_index=2,
        role="match",
        text="\x01\x02",
        matrix=(1.0, 0.0, 0.0, 1.0, 30.0, 0.0),
        literal_kind="byte",
    )
    match_segment.local_start = len("prefix")
    match_segment.local_end = len("prefix") + 2
    match_segment.width = (len(match_segment.text) / total_length) * original_run.width

    prefix_segment = _build_replacement_segment(
        operator_index=2,
        role="prefix",
        text="prefix",
        matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    prefix_segment.local_start = 0
    prefix_segment.local_end = len("prefix")

    suffix_segment = _build_replacement_segment(
        operator_index=2,
        role="suffix",
        text="suffix",
        matrix=(1.0, 0.0, 0.0, 1.0, 40.0, 0.0),
    )
    suffix_segment.local_start = len("prefix") + 2
    suffix_segment.local_end = len("prefix\x01\x02suffix")

    plan = ReplacementPlan(
        page_index=0,
        original_text="\x01\x02",
        replacement_text="CC",
        segments=[prefix_segment, match_segment, suffix_segment],
    )

    replacement = {
        "context": {"matched_text": "\x01\x02"},
        "replacement": "CC",
        "_replacement_plan": plan,
    }

    updated_runs, modified_sources, _ = renderer._apply_replacements_to_runs(
        [original_run],
        [replacement],
        doc_page=object(),
        run_id=None,
    )

    operator_record = OperatorRecord(
        index=2,
        operator=b"TJ",
        operands=([array],),
        graphics_depth=0,
        text_depth=1,
        ctm=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        text_line_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_resource="/F1",
        font_size=12.0,
        char_spacing=0.0,
        word_spacing=0.0,
        horizontal_scaling=100.0,
        leading=14.0,
        text_rise=0.0,
        text_fragments=["prefix", "\x01\x02", "suffix"],
        text_adjustments=[-40.0],
        operand_types=["string:text", "number", "string:byte", "number", "string:text"],
        literal_kind="array",
        raw_bytes=[b"prefix", b"\x01\x02", b"suffix"],
    )

    merged = renderer._merge_runs_into_content(
        original_operations,
        [original_run],
        updated_runs,
        modified_sources,
        {2: operator_record},
    )

    tj_arrays = [operands[0] for operands, operator in merged if operator == b"TJ"]
    assert len(tj_arrays) == 1

    result_array = tj_arrays[0]
    assert isinstance(result_array[1], ByteStringObject)
    assert bytes(result_array[1]) == b"CC"
    kern_values = [
        float(item)
        for item in result_array
        if isinstance(item, (NumberObject, FloatObject))
    ]
    assert kern_values == [-40.0]
