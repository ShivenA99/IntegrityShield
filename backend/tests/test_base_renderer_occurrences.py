from __future__ import annotations

import fitz

from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer


def _render_text_page(text: str, *, fontsize: float = 12.0) -> tuple[fitz.Document, fitz.Page]:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(72, 72), text, fontsize=fontsize)
    return doc, page


def test_find_occurrences_handles_missing_whitespace():
    renderer = BaseRenderer()
    doc, page = _render_text_page("indexi")
    try:
        results = renderer._find_occurrences(page, "index i")
    finally:
        doc.close()

    assert results, "Expected collapsed match when whitespace is missing"
    match = results[0]
    assert match["text"].replace(" ", "") == "indexi"
    assert match["char_start"] == 0
    assert match["char_end"] == len("indexi")


def test_find_occurrences_normalizes_accents():
    renderer = BaseRenderer()
    doc, page = _render_text_page("café")
    try:
        results = renderer._find_occurrences(page, "cafe")
    finally:
        doc.close()

    assert results, "Expected accent-normalized match"
    match = results[0]
    assert match["text"].replace(" ", "") == "café"
    assert match["char_start"] == 0
    assert match["char_end"] == len("café")


def test_locate_text_span_prefers_matched_glyph_path():
    renderer = BaseRenderer()
    doc, page = _render_text_page("2 2")
    try:
        occurrences = renderer._find_occurrences(page, "2")
        assert len(occurrences) >= 2

        second = occurrences[1]
        context = {
            "original": "2",
            "replacement": "1",
            "matched_glyph_path": {
                "block": second["block_index"],
                "line": second["line_index"],
                "span": second["span_index"],
                "char_start": second["char_start"],
                "char_end": second["char_end"],
            },
        }

        location = renderer.locate_text_span(page, context)
        assert location is not None
        matched_path = context.get("matched_glyph_path") or {}
        assert matched_path.get("char_start") == second["char_start"]
        assert matched_path.get("char_end") == second["char_end"]
        assert context.get("matched_block_index") == second["block_index"]
    finally:
        doc.close()
