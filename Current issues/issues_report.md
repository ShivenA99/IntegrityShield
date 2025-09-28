# Current Issues – PDF Manipulation Verification

This document captures the findings from the latest end-to-end runs executed on 27 Sep 2025 after restarting the backend/frontend and re-running the pipeline for every PDF in `test input pdf's/`. Each run used a blanket substring mapping that appends `" [altered]"` to the question stem so that the renderers have a deterministic replacement target.

Run metadata, renderer stats, and extracted text were pulled from `backend/data/pipeline_runs/<run_id>/structured.json` plus the regenerated overlay PDFs (`enhanced_content_stream_overlay.pdf`, `enhanced_pymupdf_overlay.pdf`). Counts below refer to the number of occurrences of the literal string `[altered]` in the selectable text layer. All renderers reported 100% “effectiveness” whenever overlays were applied, because the overlay pass completed even when the underlying text layer was not aligned with the question count.

> ⚠️  Core takeaway: both renderers produce overlay assets, but the underlying text layer does **not** include the expected replacement for many questions. The mismatch stems from upstream extraction (short stems, duplicated stems, missing spans) and from the strategy of mapping everything to the full stem text regardless of how that text renders in the PDF.

## Per-run Findings

### HW01.pdf — run `1a1592bf-86c8-47fb-b23b-b47d73161565`
- 4 questions detected, 4 substring mappings saved (full-stem).
- Renderer stats show 4 replacements but **only 2 overlays were dropped**, and only two `[altered]` hits appear in selectable text.
- Inspection: questions 1 and 2 share a similar layout; questions 3 and 4 span multi-line paragraphs that the renderer captured as separate spans. The image overlay fallback redacted the span but the new text textbox collapsed to the first line, so only two stems surface in text layer.
- Root cause: our rectangle de-duplication collapses overlapping regions; later spans fail to insert because they intersect earlier rectangles.

### Quiz6.pdf — run `99b1a960-ec6d-499b-ac21-c6f5aed1fc3d`
- 8 questions, 8 mappings, renderer logged 12 replacements (due to discovery tokens) but **only 2 `[altered]` hits**.
- Question stems are extremely short (“Which layer…?”, “What is…?”) and occur verbatim across multiple questions. The first replacement captures the stem; subsequent questions reuse the same token sequence so the renderer deduplicates the rect and overlays reuse the identical image.
- Recommendation: augment mapping with question number prefix/suffix so each replacement becomes unique.

### Quiz_3.pdf — run `a93d2c13-01a9-42c8-887b-ece165fbffa2`
- 2 long-form questions (forward algorithm + Viterbi) with paragraphs well over 200 characters.
- Overlays applied (effectiveness 1.0) but the selectable text layer contains **zero** `[altered]` strings. The PyMuPDF text insertion hit the same bounding box but failed to preserve the paragraph breaks; text extraction truncates at the newline and the suffix is beyond the fetched segment.
- Need to split long stems at sentence boundaries or inject the suffix near the beginning of the paragraph so it survives extraction.

### Quiz_7.pdf — run `c56bb75b-2c4e-472a-ae8c-42b932bc2f48`
- 8 questions, 11 `[altered]` hits. Some stems wrap twice so the suffix appears in both `content_stream_overlay` and `pymupdf_overlay` text layers.
- Although occurrences exceed the number of questions, it still indicates inconsistent span handling; the invisible text overlapped with multiple readouts.

### cybersecurity_mcq_quiz.pdf — run `1ae8d062-a3ea-495f-bdbb-0fe996c1b76c`
- OCR extracted stems as generic labels (“Question 1”, “Question 2”). Replacements therefore targeted those placeholders, not the actual prompt text.
- Both renderers skipped overlays (effectiveness 0.0). We need to revisit content discovery for this PDF—either improve OCR extraction or pull the question text from tables/options so we have a real mapping target.

### demo_paper.pdf — run `00b959e2-fe9a-4eb4-a2d4-a92a178b2d53`
- 7 questions, 7 overlays, 7 `[altered]` hits. This is the only case where selectable text matches the mapping count; multi-line stems are short and glyphs align with mapping rectangles.
- Serves as our “good” baseline.

### general_knowledge_quiz.pdf — run `65bc4796-fb7a-442e-9872-441c03c0ff7b`
- 10 questions but 14 `[altered]` hits (duplicate stems again).
- Several stems are one-liners (“Match the countries with their capitals”), repeated across sections. Without unique contexts we can’t disambiguate overlays.

### quiz_rnn.pdf — run `469417ef-cfa3-4edb-aecc-709266004277`
- 8 questions, 8 overlays, but only **one** `[altered]` hit despite per-question mappings.
- Same root cause as Quiz6: repeated stem wording across items leads to rectangle reuse, so only the first instance produces selectable text. The others render as images only.

## Cross-cutting Issues

- **Mapping strategy is naive:** applying the full stem verbatim fails whenever the OCR output is short, duplicated, or divergent from the visible layout. We need question-number prefixes, unique tokens, or span-specific bounding boxes from discovery to build reliable mappings.
- **Overlay deduplication is too aggressive:** `_ensure_non_overlapping_rect` shifts overlapping rectangles downward. When multiple stems share the same bbox (e.g., identical wording stacked vertically), subsequent insertions are discarded, leaving only the first replacement in the text layer.
- **Long-form spans exceed extraction window:** PyMuPDF returns ~4096 characters per span; appending the suffix at the end of multi-paragraph questions puts the manipulation beyond what `get_text()` returns.
- **cybersecurity quiz lacks extracted content:** indicates the structured question data is insufficient; we must revisit the content-discovery output for forms/tables.
- **UI flow remains fragile:** random mappings are still wired to `resumeFromStage`, so the UI jumps ahead if the helper is triggered. This needs decoupling (not addressed yet).
- **Visual overlays succeed even when replacements fail:** the raster layer hides issues during eyeball checks; the text layer is the accurate source of truth.

## Next Remediation Steps

1. Rework the mapping generator to include question metadata (e.g., `Q1: <stem>`) or insert unique markers per question, eliminating dedup collisions.
2. For multi-line stems, split mappings per span or place the suffix at the start of the stem to survive text extraction.
3. Enhance `_ensure_non_overlapping_rect` to offset rectangles horizontally/vertically and always insert a textbox even if overlap occurs; log suppression events.
4. Improve content discovery for PDFs that returned “Question 1/2” placeholders—likely need table parsing or fallback to option text when stems are blank.
5. Adjust the Smart Substitution UI so helper buttons do **not** auto-resume the pipeline (resume should live behind an explicit “Continue” CTA).
6. Add renderer regression tests that count `[altered]` hits against question counts so we catch missing replacements automatically.

---

Generated by `backend/.venv/bin/python` scripts inspecting `structured.json` and overlay PDFs created on 2025-09-27.
