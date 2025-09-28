from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.services.pipeline.enhancement_methods.pymupdf_renderer import PyMuPDFRenderer
from app.services.pipeline.enhancement_methods.content_stream_renderer import ContentStreamRenderer

RUN_ID = "4bc3baad-0af1-48b3-946d-3923cfcb2aab"
PDF_NAME = "Quiz6.pdf"


@pytest.mark.parametrize("renderer_cls", [PyMuPDFRenderer, ContentStreamRenderer])
def test_renderer_rewrites_are_precise(renderer_cls, tmp_path):
    base_dir = (
        Path(__file__).resolve().parent
        / "data"
        / "pipeline_runs"
        / RUN_ID
    )
    original_pdf = base_dir / PDF_NAME
    assert original_pdf.exists(), f"Missing test PDF at {original_pdf}"

    renderer = renderer_cls()
    mapping = renderer.build_mapping_from_questions(RUN_ID)
    mapping_context = renderer.build_mapping_context(RUN_ID)

    destination = tmp_path / f"{renderer_cls.__name__}.pdf"
    stats = renderer.render(RUN_ID, original_pdf, destination, mapping)

    output_bytes = destination.read_bytes()
    renderer.validate_output_with_context(output_bytes, mapping_context, RUN_ID)

    assert stats.get("replacements", 0) > 0, "Renderer did not perform any replacements"

    doc = fitz.open(stream=output_bytes, filetype="pdf")
    try:
        for contexts in mapping_context.values():
            for ctx in contexts:
                page_idx = ctx.get("page")
                bbox = ctx.get("stem_bbox") or ctx.get("bbox")
                replacement = renderer.strip_zero_width(str(ctx.get("replacement") or "")).strip()
                if not isinstance(page_idx, int) or not bbox or not replacement:
                    continue
                if page_idx < 0 or page_idx >= len(doc):
                    continue
                rect = fitz.Rect(*bbox)
                rect = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
                text = doc[page_idx].get_text("text", clip=rect) or ""
                normalized = renderer.strip_zero_width(text).strip().casefold()
                assert replacement.casefold() in normalized, (
                    f"Replacement '{replacement}' not selectable on page {page_idx + 1}"
                )
    finally:
        doc.close()
