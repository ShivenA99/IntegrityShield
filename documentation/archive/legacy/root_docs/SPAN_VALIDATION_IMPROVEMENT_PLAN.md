# Span Validation & Replacement Hardening Plan

This memo captures the detailed roadmap for making every smart-substitution mapping
survive the content-stream rewrite pass. It builds on the latest rerun of
`f5233de4-4ab9-4283-92c9-9b7b2a88b7d7`, where six of nine mappings rendered
successfully after we relaxed span validation and reflowed the PDF in-context.

## 1. Current Signals

| Mapping | Result | Notes |
| --- | --- | --- |
| `worst-case → best-case` | ✅ | Geometry captured; full span rewrite works. |
| `3 → 5` | ✅ | Simple numeric swap remained intact. |
| `true → false` | ✅ | Interior substring (`betrue?`) now adjusts offsets correctly. |
| `crucial → detrimental` | ✅ | Hyphenated span handled after reflow. |
| `always → never` | ✅ | Interior substring inside `alwayshold` now aligns. |
| `2 → 1` (question header) | ✅ | Matches the first occurrence (`University of Batna 2`); needs disambiguation. |
| `O(n log n) → O(n)` | ⚠️ not found | Span collapsed to `O(nlogn)`; validator can’t locate literal substring. |
| `O(n) → O(1)` & `O(n) → O(n^2)` | ⚠️ dropped | Mapping spans multiple `TJ` fragments; validator sees per-fragment mismatch. |
| `index i → index i (1-based indexing)` | ⚠️ dropped | Stream stores `indexi`; space missing. |

## 2. Instrumentation Status

- Span rewrite now logs every rejection (`span replacement dropped after validation`) with page/block/span, observed text, and operator index.
- Rerunning the renderer under an app context produces usable artifacts:
  - `enhanced_content_stream_span_overlay_retry.pdf`
  - Updated `span_plan.json` with six populated entries.
- Warnings already isolate the stubborn spans by operator index.

## 3. Implementation Roadmap

### Step 1 – Guarantee Geometry Capture When Mappings Are Saved

1. **Backend (SmartSubstitutionService):**
   - Call `_enrich_selection_geometry` immediately after auto-generation and after manual edits (bulk save, single update).
   - When geometry cannot be resolved, log `auto_generate geometry locate failed` with the stem slice, so we can adjust prompts.
2. **API layer (`questions_routes.auto_generate_mappings` / `bulk_save_mappings`):**
   - Persist the enriched entry (`selection_page`, `selection_bbox`, optional `matched_glyph_path`).
3. **Frontend (SmartSubstitutionPanel / QuestionViewer):**
   - Request geometry from the backend and keep it when the user edits a mapping.
   - Visually flag mappings without geometry so the user knows they may fail.
4. **Fusion stage (GPT-5 integration):**
   - For each Vision question, gather the spans whose rectangles overlap the Vision bbox (with a small margin) to build a tiny candidate list.
   - Send that question-specific span window to GPT-5 so it returns the ordered span ids + union bbox; persist the result (Vision stem text stays untouched).
   - Update the GPT response schema to return `stem_spans`: ordered span ids plus the unioned bbox.
   - Smart Reading must persist those ids in `question_index[*].stem_spans` and use their union as the canonical `stem_bbox`.
   - When we rebuild mapping contexts, feed the recorded span ids directly into `_match_contexts_on_page` (skip the clip-rect filter) so literal matching works even when stems wrap across multiple lines.

### Step 2 – Normalized Text Matching

1. **Span context builder:** extend `_build_span_context` to store a normalized string (ligatures removed, whitespace collapsed) and include `fingerprint_key` in the mapping.
2. **Validator (`SpanRewriteAccumulator.build_entry`):**
   - Already collapses diacritics; add a secondary check using the span’s normalized text so `O(n log n)` matches `O(nlogn)`.
3. **Occurrence resolver (`BaseRenderer.locate_text_span`):**
   - When a literal substring is missing, fall back to matching the normalized string and use the existing `collapse_with_index` map to capture the correct indices.

### Step 3 – Multi-Fragment and Interior Replacements

1. **Planner (`match_planner.py`):** detect when a mapping spans consecutive fragments and merge them into a single slice group before passing to the renderer.
2. **Renderer:** if multiple fragments are supplied for one mapping, confirm they belong to the same span and apply the replacement once over the merged range.
3. **Single-character disambiguation:** when the mapping is a bare digit or symbol, fall back to the GPT-provided geometry to avoid matching headers or numbering.

### Step 4 – Mappings with Missing Spaces

1. Allow controlled relaxation if collapse(original) == collapse(observed) and geometry is present (already partially implemented).
2. When we reinsert spaces in replacements (e.g., `index i (1-based indexing)`), ensure the planner distributes kerning across the original fragments so the overlay matches the desired spacing.

### Step 5 – Test & Iterate

1. Re-run `pdf_creation` for `f5233de4-4ab9-4283-92c9-9b7b2a88b7d7` inside a Flask app context (`PYTHONPATH=backend backend/.venv/bin/python …`).
2. Inspect warnings; there should be none once all steps land.
3. Verify the final PDF and span plan include all nine mappings (no fallbacks).

### Step 6 – Update Documentation / Regression Cases

- Document geometry requirements for GPT prompts (include span bounding boxes and block/line/span indices).
- Capture example failures (ligature, multiple fragments, missing space) in `STREAM_REWRITE_PROGRESS.md` so future runs can double-check.
- Add tests for `_enrich_selection_geometry` to confirm selection info is stored when geometry exists.

## 4. Open Questions

- Do we want to auto-clear the risky single-character mappings (like question numbers) or ask the user to provide more context?
- Should we promote the normalized string matching to the planner stage so we can calculate the correct occurrence index earlier?

This plan keeps GPT responsible only for identifying which span to change, while our deterministic code handles geometry, fonts, and operator surgery.
