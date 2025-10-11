# Stream Rewrite – Research Context & Next Steps

## Objective
Replace the fragile courier/kerning hack in the stream rewrite stage with a deterministic PDF content revamp. The new pipeline must: (1) scale courier replacements to match original widths; (2) resume the suffix at the exact original matrix without negative kerning; (3) preserve copy/paste order prefix → replacement → suffix.

## Summary Of Current Work
- Added `TextRun` dataclass and matrix helpers in `backend/app/services/pipeline/enhancement_methods/base_renderer.py`.
- Swapped `_rebuild_operations_with_courier_font` for a rebuild routine that harvests text spans, applies replacements, and emits a fresh `BT/Tm/Tj` sequence.
- Introduced utilities: `_extract_page_spans`, `_build_font_resource_map`, `_extract_runs_from_spans`, `_measure_run_substring_width`, `_generate_runs_operations`.

## Current State
- `_parse_text_runs` has been sidelined (returns `[]`); the new pipeline attempts to reconstruct entirely from PyMuPDF span data.
- Stream regeneration currently only adds the replacement and nearby spans; the rest of the page isn't re-emitted. As a result `after_stream_rewrite.pdf` is incomplete (only the replacement spans render).
- Font/resource mapping and width estimation use PyMuPDF spans but need refining so non-replaced text is preserved.
- Redaction overlay path still uses PyMuPDF `insert_textbox`; actual-text injection remains future work.

## Next Steps
1. Ensure all original spans are re-emitted before replacements: resurrect `_parse_text_runs` or augment `_extract_runs_from_spans` so the entire page content is rebuilt.
2. Confirm font resource mapping aligns with `/Font` dictionary names; fix actual font selection when restoring `Tf`.
3. Once the new stream is stable, adjust suffix/replacement positioning logic to guarantee correct matrix resume.
4. Later, wrap redaction overlays in marked content (`BDC/EMC`) with `/ActualText` to stabilize extraction.

Review `documentation/stream_rewrite_brief.md` for a detailed problem analysis and research questions.
