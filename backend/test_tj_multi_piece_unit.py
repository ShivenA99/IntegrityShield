"""Unit tests ensuring TJ replacements handle multi-piece and single-piece spans."""

import logging

from PyPDF2.generic import ArrayObject, FloatObject, NumberObject, TextStringObject

from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer


class DummyRenderer(BaseRenderer):
    """Expose protected helpers for unit testing without full app context."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("DummyRenderer")


def _collect_text(operations):
    text = []
    for operands, operator in operations:
        if operator == b"TJ":
            sequence = operands[0]
        elif operator == b"Tj":
            sequence = [operands[0]]
        else:
            continue
        for item in sequence:
            if isinstance(item, TextStringObject):
                text.append(str(item))
    return "".join(text)


def _extract_first_suffix_array(operations):
    for operands, operator in operations:
        if operator == b"TJ":
            return operands[0]
    return ArrayObject()


def test_multi_piece_tj_replacement_preserves_suffix_alignment():
    renderer = DummyRenderer()

    tj_array = ArrayObject(
        [
            TextStringObject("prefix "),
            TextStringObject("be"),
            NumberObject(-40),
            TextStringObject("ne"),
            NumberObject(-30),
            TextStringObject("fit"),
            NumberObject(-20),
            TextStringObject(" suffix"),
        ]
    )

    aggregated_text, pieces = renderer._build_tj_piece_map(tj_array)
    original_text = "benefit"
    replacement_text = "demerit"

    task = {
        "original_text": original_text,
        "replacement": replacement_text,
        "original_width": 70.0,
        "font_size": 9.0,
        "context": {
            "prefix": "prefix ",
            "suffix": " suffix",
            "q_number": "1",
        },
        "stream_start": aggregated_text.index(original_text),
        "global_start": aggregated_text.index(original_text),
    }

    match_start = renderer._resolve_tj_match_start(aggregated_text, task, segment_start=0)
    assert match_start == aggregated_text.index(original_text)

    match_info = renderer._map_match_to_pieces(
        pieces,
        match_start,
        match_start + len(original_text),
    )
    assert match_info and match_info["spans_multiple_pieces"] is True

    segment = {
        "text": aggregated_text,
        "font_context": {"font": "/F1", "fontsize": 9.0},
    }

    operations = renderer._execute_precision_width_replacement(
        tj_array,
        match_info,
        task,
        segment,
        run_id="unit-test",
    )

    courier_switches = [
        operands
        for operands, operator in operations
        if operator == b"Tf" and operands and str(operands[0]) == "/Courier"
    ]
    assert courier_switches

    rebuilt_text = _collect_text(operations)
    assert "prefix demerit suffix" in rebuilt_text
    assert "benefit" not in rebuilt_text

    suffix_array = _extract_first_suffix_array(operations[-1:])
    suffix_text_items = [item for item in suffix_array if isinstance(item, TextStringObject)]
    assert suffix_text_items and str(suffix_text_items[0]).startswith(" suffix")


def test_single_piece_replacement_keeps_suffix_spacing():
    renderer = DummyRenderer()

    tj_array = ArrayObject(
        [
            TextStringObject("the primary"),
            NumberObject(-200),
            TextStringObject(" remainder"),
        ]
    )

    aggregated_text, pieces = renderer._build_tj_piece_map(tj_array)
    original_text = "the"
    replacement_text = "not"

    task = {
        "original_text": original_text,
        "replacement": replacement_text,
        "original_width": 18.0,
        "font_size": 9.0,
        "context": {
            "prefix": "",
            "suffix": " primary",
            "q_number": "1",
        },
        "stream_start": aggregated_text.index(original_text),
        "global_start": aggregated_text.index(original_text),
    }

    match_start = renderer._resolve_tj_match_start(aggregated_text, task, segment_start=0)
    assert match_start == 0

    match_info = renderer._map_match_to_pieces(
        pieces,
        match_start,
        match_start + len(original_text),
    )
    assert match_info and match_info["spans_multiple_pieces"] is False

    segment = {
        "text": aggregated_text,
        "font_context": {"font": "/F1", "fontsize": 9.0},
    }

    operations = renderer._execute_precision_width_replacement(
        tj_array,
        match_info,
        task,
        segment,
        run_id="unit-test-single",
    )

    rebuilt_text = _collect_text(operations)
    assert "not primary remainder" in rebuilt_text

    last_suffix_array = _extract_first_suffix_array(operations[-1:])
    text_items = [item for item in last_suffix_array if isinstance(item, TextStringObject)]
    assert text_items, "Expected suffix text"
    assert str(text_items[0]).startswith(" primary"), "Suffix should start with original word"

    # Ensure any numeric kerning leading the suffix remains before the text
    numeric_items = [item for item in last_suffix_array if isinstance(item, (NumberObject, FloatObject))]
    if numeric_items:
        first_item = last_suffix_array[0]
        assert isinstance(first_item, NumberObject), "Kerning should precede suffix text"
