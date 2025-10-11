# Stream Rewrite Progress Snapshot

This document captures the current state of the stream-rewrite refactor so the next Codex session can resume seamlessly. Use it alongside `COMPREHENSIVE_STREAM_REWRITE_PLAN.md`.

## 1. Current Status
- **Phase A (Instrumentation)** – Complete. Operator records, span alignment, and diagnostics (advance vectors, world-space matrices, suffix drift) are in place.
- **Phase B (Replacement Planning)** – In progress. Planner emits prefix/match/suffix segments with derived matrices/fonts/widths; base renderer attaches segments to `TextRun` and uses them for prefix/match/suffix emission. Remaining tasks are outlined below.
- **Phase C (Operator Surgery)** – In progress. Inline rewrite paths handle single-operator `Tj`/`TJ` edits, and isolation fallback now covers matrix/width drift plus planner-forced zero-length array matches.
- **Span Overlay Integration** – Updated. Overlay renderer now samples the rewritten page snapshot so replacement spans persist visually; raster fallback remains only for error paths. Pending: address ligature spacing in the rewritten content itself (see Phase C item 7).
- **Phases D–F** – Not started.
- Environment setup/tests executed 2025-10-02 (`python3 -m venv backend/.venv`; `pip install -r backend/requirements.txt`; pytest targets below all pass).

## 2. Key Files & Artifacts
- `backend/app/services/pipeline/enhancement_methods/base_renderer.py`
  * `TextRun` carries planner metadata (`plan_segment`, `rewrite_context`).
  * `_apply_replacements_to_runs` uses planner segment data for prefix/match/suffix, including segment matrices/fonts.
 * `_emit_run_operations` consumes planner matrices/fonts when available, and isolation fallback now recognises planner-forced placeholders to remove zero-length `TJ` matches without emitting inline arrays.
- `backend/app/services/pipeline/enhancement_methods/match_planner.py`
  * Match segments now retain `planned_replacement` text, raw replacement offsets, per-slice extent bounds, and operator fragment layouts so downstream rewrite code no longer relies on difflib heuristics.
  * Added regression coverage for tail-growth spans and operator fragment allocation (`backend/test_match_planner.py::test_segment_records_replacement_offsets_and_fragments_for_tail_growth`).
- `backend/app/services/pipeline/enhancement_methods/match_planner.py`
  * Builds `ReplacementPlan` with prefix/match/suffix segments (`ReplacementSegment`) capturing span slices, matrices, font resource, font size, width, and target range offsets. Zero-length match slices on `TJ` operators are now tagged with `requires_isolation=True` so downstream surgery can force BT/ET isolation.
- `backend/app/services/pipeline/enhancement_methods/content_state_tracker.py`
  * records world-space start/end, advance vectors, suffix drift.
- `backend/app/services/pipeline/enhancement_methods/stream_analysis.py`
  * orchestrates span alignment and annotates records with drift diagnostics; warnings logged when tolerance exceeded.
- Plan file: `COMPREHENSIVE_STREAM_REWRITE_PLAN.md` (Phase tracker + progress notes).

## 3. Outstanding Work (Detailed Checklist)

### Phase B – Replacement Planning Enhancements
1. **Integrate planner segments into operation merge** – ✅ Done
   - `_merge_runs_into_content` now initializes state from operator records and reuses planner segments without generic rebuilds.
   - Added unit coverage to lock in the behaviour (`backend/test_merge_runs_into_content.py`).

2. **Planner matrix usage for replacements** – ✅ Done
   - Width tolerance guard added (planner vs span-measured). Verified via `backend/.venv/bin/python3.13 -m pytest backend/test_merge_runs_into_content.py -q`.

3. **Font resource management** (overlaps Phase D) – ✅ Done for planner-driven fonts
  - New helper injects missing font resources into page dictionaries; add follow-up diagnostics once Phase D refines fallback strategy.
4. **Persist fragment plan metadata for span overlays** – ✅ Done
   - Replacement segments now store operator fragment layouts, per-slice bounds, and raw replacement offsets; span-plan JSON surfaces these fields (including overlay fallbacks) for diagnostics.
   - Tests `backend/tests/test_span_overlay_plan.py::test_collect_span_plan_allocates_tail_insert_correctly` and `::test_operator_rewrite_streams_fragment_plan_without_truncation` validate smart substitution against the LLM operator 71 regression.

### Phase C – Operator Surgery Logic (pending)
4. **Preserve planner context before surgery** – ✅ Done
   - ✅ `_plan_replacements` now records the covering segment/operator indices, and `_reconstruct_page_operations` filters `build_replacement_plan` using those hints. Repeated tokens (e.g., `RNNs` in run `cbfead67…`) no longer fall back to naive substring search, so the title stays untouched.
   - ✅ When the fallback does trigger, we now log the operator hints to make the problem visible instead of silently rewriting the wrong run.
   - ✅ Isolation-specific helper keeps `TJ` arrays when surgery isolates the run, preserving numeric adjustments and literal types so kerning survives even when width/matrix drift forces BT/ET fallback.

5. **Single-operator rewrite path** – ✅ Done
   - Inline `Tj` replacements reuse the original operator when fonts + widths align; added inline `TJ` array rewrite that preserves interstitial kerning numbers and literal/byte style.
   - New helper maps planner segments onto array tokens; regression covered by `backend/test_merge_runs_into_content.py::test_tj_array_inline_rewrite_preserves_kern_adjustments`.

6. **Isolated replacement path** – 🔄 In Progress
   - Isolation now triggers when planner matrices/widths diverge, emitting `ET/BT` blocks that apply planner-derived font + spacing before the replacement and restore the original state afterwards.
   - `_build_isolated_replacement` reinstates `Tc`, `Tw`, `Tz`, `Ts`, and `Tm` from planner/original metadata; regressions captured in `backend/test_merge_runs_into_content.py::test_isolation_restores_state_with_planner_metadata` and `::test_cross_operator_replacement_uses_isolation_and_preserves_sequence`.
   - Mixed literal/hex arrays now retain byte operands during inline surgery (`test_tj_array_inline_rewrite_preserves_byte_literal_segments`) and isolation fallback keeps those operands as `ByteStringObject` when width tolerances are exceeded or literal-only operators fire (`test_isolation_preserves_byte_literals_when_width_mismatch`, `test_tj_byte_literal_isolation_emits_byte_string`). Planner-flagged zero-length `TJ` match slices now force isolation via placeholder runs so deletions stay deterministic (`test_tj_deletion_forces_isolation_when_segment_requests_it`).
   - Inline `TJ` rewrites now refuse disjoint match spans so multi-match arrays drop into isolation (`test_tj_array_inline_rewrite_rejects_disjoint_match_segments`), keeping prefix/middle/suffix order intact.
   - Verified on run `cbfead67-4428-4e01-aef5-b5566472f2e3` that deleting the entire `TJ` record emits isolation `BT/ET` blocks (see ad-hoc script in `backend/` capturing segment `159`).
    - Planner-driven deletions across operators succeed (`test_cross_operator_deletion_removes_segments_and_restores_suffix`).
    - ✅ New isolation array constructor keeps intra-match kerning adjustments, covered by `backend/test_merge_runs_into_content.py::test_isolation_tj_preserves_internal_kern_adjustments`.
    - ✅ Prefix segments emitted during isolation now rebuild `TJ` arrays only when kerning/byte data exists, preserving original numeric adjustments while leaving simpler prefixes as `Tj` (`test_isolation_prefix_tj_reuses_original_kern_values`).
    - ✅ Suffix isolation retains trailing kerning adjustments by reusing `TJ` arrays when needed (`backend/test_merge_runs_into_content.py::test_isolation_suffix_tj_preserves_trailing_kern_values`).
    - ✅ Non-array fallback now emits `Tj` operands as `ByteStringObject` when planner segments mark byte literals, preventing silent text-mode conversions (`test_emit_run_operations_uses_bytestring_for_byte_literal_tj`).
    - ✅ Multi-span match segments now split so each inherits its span matrix and replacement slice (`backend/test_match_planner.py::test_match_segments_split_when_spans_have_distinct_matrices`).
    - ✅ Hex-only isolation fallback now reuses operator matrices when span geometry is missing; covered by `backend/test_match_planner.py::test_hex_only_match_segment_uses_record_matrix_when_span_missing_geometry`.
    - ✅ Mixed literal deletions split along literal-kind boundaries so byte/text fragments force isolation individually (`backend/test_match_planner.py::test_mixed_literal_deletion_forces_isolation_per_fragment`).
    - ✅ Re-ran `stream_analysis` on run `cbfead67-4428-4e01-aef5-b5566472f2e3` (`backend/.venv/bin/python3.13 - <<PY …`)—overlay output now reports 1 alignment warning (page-level notice) and zero suffix drift.
    - ✅ Added `backend/test_stream_analysis.py::test_stream_analysis_reports_single_warning_when_spans_missing` to lock in the page-level fallback behaviour for missing spans.
    - ✅ Span extractor now harvests text from character lists, ignores synthetic glyphs, and alignment falls back to partial prefixes to keep diagnostics clean.
    - ✅ Synthetic advance metrics now bridge truncated PyMuPDF spans so `stream_analysis` runs without warnings; guarded by `backend/test_stream_analysis.py::test_stream_analysis_synthesizes_metrics_for_unaligned_text`.
    - ✅ Match runs now carry measured replacement widths from span char maps so inline `TJ` rewrites can reconcile planner widths.
    - ✅ Inline `TJ` surgery pads width via compensating kerning when replacements shrink the glyph span (skipping byte segments); covered by `backend/test_merge_runs_into_content.py::test_tj_array_inline_rewrite_pads_width_with_kerning`.
    - ✅ Run `48807c82-8b5d-4954-8de7-2ec66510bdb2` diagnostics confirmed suffix clipping stemmed from unadjusted inline widths; post-fix kerning keeps suffix matrices aligned with original positions.
7. **Span-level rewrite accuracy** – 🔄 In Progress
    - Span plan swaps still drive the overlay pipeline (vector snapshot instead of original PDF rects). Re-ran `f6b51fa3-ae29-4058-a9ad-04ed1b2412a9` and confirmed the regenerated `enhanced_content_stream_span_overlay.pdf` matches the prior raster overlay while the rewritten content stream holds the substitutions.
    - `SpanRewriteEntry` now records per-fragment replacements (`fragment_rewrites`), and `_map_replacement_to_text_fragments` redistributes replacements over the original operator fragments. Unchanged `ByteStringObject`/`TextStringObject` operands are reused so ligature bytes survive; changed fragments emit the same literal kind. `after_span_rewrite.pdf` for the run above now extracts natural strings (“What is not primary…”, “dependencies?”) without the earlier ligature breaks.
    - Width handling now keeps existing kerning numbers when the per-fragment delta is ≤ 50 units; larger deltas fall back to a bounded `Tz` scale computed from the span widths (`original_width / replacement_width`, clamped to [0.5, 1.5]). This retains kerning for close fits while avoiding the oversized Courier fallback when replacements shrink spans dramatically.
    - Diagnostics: span plans now surface fragment-level metadata in `span_plan.json`, and `SpanOverlayRenderer` continues to emit overlay artifacts plus the regenerated span plan for downstream tooling.
    - Tests rerun: `backend/.venv/bin/python3.13 -m pytest backend/test_merge_runs_into_content.py backend/test_tj_multi_piece_unit.py backend/test_stream_analysis.py -q`.
    - TODO: realign `build_mapping_context` offsets with the normalized span stream so planner segments start/end on the intended glyphs, persist `matched_glyph_path` hints, and let fragment mapping allocate extra array entries when replacements add characters. After that, spot-check multi-page kerning cases and add a regression that verifies fragment reuse for byte-heavy `TJ` arrays.

- 2025-10-08 (Span overlay pivot): Investigation of run `de3d91e8-2ed9-404c-9141-b8544414f2a2` confirmed inline kerning fallbacks truncate replacements and require unsustainably large kern deltas. We prioritised the span-level rewrite → overlay pipeline but *did not persist raw replacement slice metadata or fragment layouts*, so downstream code began recomputing slice boundaries heuristically. This is the origin of the truncation/splitting issues now observed (e.g., operator 71 losing the “n” in `short-term`).
- 2025-10-08: Implemented span plan capture (`SpanRewriteEntry`) and new `SpanOverlayRenderer`. `rewrite_content_streams_structured` now records per-page span plans; `rewrite_spans_only` rewrites whole spans while preserving operator order and optional scaling. PDF creation pipeline includes a new method (`content_stream_span_overlay`) that emits `stream_rewrite_overlay_span` artifacts plus JSON span plans. **Note:** plan entries currently lack raw slice offsets/fragment metadata, so `_collect_span_rewrite_from_plan` and `_remap_fragments_by_diff` must reconstruct that information, leading to the bugs outlined in the reassessment below. Next target revisited: persist full offsets + fragment metadata so downstream steps consume authoritative data.
- 2025-10-08: Added GPT-5 auto-mapping support – backend endpoint (`/auto_generate`) calls ExternalAIClient with structured stem/options and stores normalized mappings. UI now exposes “Auto-generate” per-question (updates mapping table, preserves validation workflow). Results panel surfaces span overlay stats (applied/targets/coverage) and links to span-plan artifacts. Tests re-run (same suite). Next target: add bulk automation controls in smart substitution panel and wire validation badges across the pipeline summary.

### Phase D – Resource & Font Management (pending)
6. **Courier fallback removal**
   - Remove placeholder `SpecialCourier` usage; rely on planner or original font unless isolation requires fallback.

### Phase E – Safety & Validation (pending)
7. **Diagnostics**
   - After rewrite, rerun `stream_analysis` to validate suffix drift ≤ tolerance.
   - Capture logs for any residual warnings.

### Phase F – Testing Matrix (pending)
8. **Unit/Integration Tests**
   - Add tests covering planner integration, cross-operator replacements, and no-op behaviour when planning absent.
   - ✅ `backend/test_merge_runs_into_content.py` extended to ensure inline `TJ` surgery keeps kerning adjustments intact.
   - ✅ Isolation regressions now include planner text-state preservation, cross-operator sequencing, and kerning-aware TJ isolation (`test_isolation_restores_state_with_planner_metadata`, `test_cross_operator_replacement_uses_isolation_and_preserves_sequence`, `test_isolation_tj_preserves_internal_kern_adjustments`, `test_isolation_prefix_tj_reuses_original_kern_values`, `test_isolation_suffix_tj_preserves_trailing_kern_values`, `test_emit_run_operations_uses_bytestring_for_byte_literal_tj`).

## 4. Environment Setup TODO (after code changes)
1. Create virtual environment (e.g., `python3 -m venv .venv`).
2. `pip install -r requirements.txt`.
3. Run project tests (pytest or repo-specific commands).
4. Capture commands/result logs for future sessions.

## 5. Quick Start for Next Session
1. Review `COMPREHENSIVE_STREAM_REWRITE_PLAN.md` and Section 3 above.
2. Patch `build_mapping_context` / `_plan_replacements` so spaced question stems project through normalized span indices (store raw + normalized bounds and glyph paths).
3. Extend `_map_replacement_to_text_fragments` (and planner segment assembly) to create additional array fragments when replacements introduce new glyphs; add regression coverage with a byte-literal heavy `TJ` sample.
4. Re-run end-to-end on runs `f6b51fa3-ae29-4058-a9ad-04ed1b2412a9` and `de3d91e8-2ed9-404c-9141-b8544414f2a2`, confirming both text extraction and overlays remain stable after the alignment fixes.
5. Re-run `stream_analysis` on pipeline samples to confirm synthetic metrics stay within tolerance and decide if `/ToUnicode` + width tables still need to be copied to restore glyph coverage; use the results to draft the Phase D kickoff checklist (font diagnostics / fallback removal).

- Last updated: 2025-10-05 (operator rebuild + kerning reset).
- Author: Codex session (Matrix Isolation refactor).

## 6. Latest Updates – 2025-10-05
- `_build_span_operator_rewrite` now rebuilds each touched operator from the combined span replacement text. We aggregate per-operator slice replacements, track kerning breakpoints with the original `text_adjustments`, and emit fresh operands with literal spaces so stale kerning arrays no longer delete glyphs.
- Fragment bookkeeping collapses to a single entry per operator while preserving literal kind; `SpanRewriteEntry.fragment_rewrites` captures the pre/post strings for debugging.
- Verified `backend/tests/test_span_overlay_plan.py` and `backend/test_stream_analysis.py` via `PYTHONPATH=backend backend/.venv/bin/python3.13 -m pytest ... -q`.
- Regenerated run `60a6b3a2-4a93-4cc8-aba2-d966466ba800`; inspected `artifacts/stream_rewrite-overlay/final.pdf` to confirm span rewrites render with the correct spacing (no more `C N N` / missing letters).
- Rebuilt the span rewrite so every replacement emits the text in Courier with a size derived from the original span width; ligature control codes (e.g., `\f` for `fi`) are expanded before encoding so we no longer drop glyphs when we leave the subset font.
- Geometry-backed replacements now respect the mapping start hints when no planner slices are available. `_build_span_operator_rewrite` replays the mapping list to rebuild the operator literal and only falls back to slice offsets when planner metadata exists, so casing like “primary” stays intact while the intended token (“the” → “not”) swaps cleanly.
- 2025-10-05: Overlay pass now caches full line rectangles from the source PDF and pastes a single bitmap per affected line, ensuring pixel-perfect restoration without re-alignment math. Awaiting verification on run `60a6b3a2-4a93-4cc8-aba2-d966466ba800` after regeneration.
- 2025-10-05: Auto-generate prompt tightened (explicit JSON schema, span-aligned offsets) and test harness added; awaiting verified GPT run once outbound network access is available.

### Active Issues
- Multi-word auto-generated mappings still risk misaligned courier rewrites when geometry is incomplete. We hardened `_enrich_selection_geometry` to fall back to text-only spans instead of aborting, but we still need a network-enabled run to confirm glyph alignment against live GPT-5 output before closing this out.
- Fresh GPT-5 integration now triggers automatically during the smart-substitution pipeline, but we have not yet validated a full run with real model responses because the current sandbox blocks outbound calls. Once network access is restored, rerun the preview harness to capture the raw payload and verify the UI consumes the enriched mappings end-to-end.
- **NEW (run f4731fb7-4ce3-4733-9e80-602579438db2)** – Smart Substitution UI now drives per-question GPT-5 calls, but only seven of the generated mappings actually made it through the rewrite/overlay pass, and two of those replacements are semantically wrong. Network flakiness during generation also caused fallbacks that the heuristic path could not repair. Next session must debug why the remaining mappings were dropped before the PDF overlay and tighten span validation so we refuse obviously bad swaps.
- **NEW (geometry hand-off via OpenAI Vision)** – Several recent runs (e.g., `81949880…`, `3b5c63e8…`) skipped every stream rewrite because the question-level `stem_bbox` covered only the first line of the stem. Instead of GPT-5 we now re-use OpenAI Vision to supply per-mapping geometry:
  1. **Vision owns text.** Smart Reading already extracts question stems/options plus bounding boxes for each question.
  2. **Mapping generation.** Smart Substitution produces GPT mappings (`start_pos`/`end_pos`, original substring, replacement).
  3. **Vision geometry refresh.** After mappings are stored, call OpenAI Vision again per page with the question context and the exact mapping substring to retrieve the bounding box for that substring.
  4. **Deterministic span lookup.** Use the Vision-provided mapping bbox (expanded by ±8–10 pt) to collect overlapping PyMuPDF spans and map the mapping offsets to precise span ids/glyphs.
  5. **Persist per-mapping span ids.** Store span ids/union bbox per mapping so pdf creation can rewrite and overlay deterministically.
  6. If Vision can’t find the substring, log a warning and fall back to the token-based matcher so the pipeline does not stall.
- **RESOLVED (run d09f5146-ecc3-42cd-b97c-328b44c83dd4)** – Rerun bootstrap now preserves an empty `enhanced_pdfs` scaffold and sanitized debug block, letting pdf_creation repopulate everything. `structured.json` and the DB row both carry fresh overlay stats immediately after the rerun+PDF flow, and the UI should surface the replacements again. Follow-up: span-plan summaries still report `{entries: 1}` even when render stats show all 9 swaps; investigate whether the summary should reflect replacement count or just page coverage before closing this out.
- **DONE (content-stream multi-operator rewrite)** – Q2 in run `5bd72aac-189c-4b0a-a2f2-2b7298c669eb` no longer leaks trailing fragments. `_process_tj_replacements` now collects the full operator window, merges text fragments across TJ/Tj literals, drops kerning entries that fall entirely inside the deleted span, and writes the replacement back once while preserving each literal's kind (byte vs. text). Segment metadata (`text`, `kern_map`, `modified`) stays in sync with the rewritten array. Added regression coverage in `backend/tests/test_span_overlay_plan.py::test_multi_operator_tj_replacement_merges_literals_cleanly` so multi-literal spans emit the replacement exactly once. Next validation: rerun `5bd72aac…` through PDF creation to double-check the overlay snapshot once the full pipeline can be exercised in an app context.

## 7. Latest Updates – 2025-10-05
- Locked in the multi-operator rewrite: `_process_tj_replacements` now merges contiguous TJ/Tj literals before splicing replacements, preserves surviving kerning numbers outside the edit window, and keeps byte literals as bytes. Added regression `backend/tests/test_span_overlay_plan.py::test_multi_operator_tj_replacement_merges_literals_cleanly`; the new test passes under `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_span_overlay_plan.py::test_multi_operator_tj_replacement_merges_literals_cleanly -q`. The broader span-overlay suite still needs the PyMuPDF glyph helpers (`_collect_span_rewrite_from_plan`, `_remap_fragments_by_diff`) wired back in before the full command in the plan goes green.
- Reworked GPT-5 completion budgets in `SmartSubstitutionService.auto_generate_for_question`: we still log `reason`/`error` metadata on fallback, but now allow up to ~4k completion tokens (and surface a preview snippet) so long-form stems no longer truncate.
- `_enrich_selection_geometry` no longer raises when the PDF page, positioning, or span lookup fails. Instead we log the condition, retain the textual offsets, and return the normalized mapping so the pipeline and API don’t die on missing geometry.
- Attempted to run `run_auto_mapping_preview.py` locally but network access is still denied (`APIConnectionError`). Logged timestamps and retry traces above so the next network-enabled session can reproduce quickly.
- Smart Substitution UI now uses per-question GPT-5 generation: each card has a “Generate” button that overwrites the existing mapping (with a live spinner) and only the “Proceed to PDF Creation” action advances the pipeline once you are satisfied with the edits.

### 7a. Span Rewrite Hardening (2025-10-06)
- Added validation logging inside the span plan so each rejected slice reports page/block/span and the observed vs. expected text.
- After re-running `pdf_creation` for run `f5233de4-4ab9-4283-92c9-9b7b2a88b7d7`, six of nine mappings now render (`worst-case`, `true`, `crucial`, `always`, etc.). The warnings highlight the remaining failure cases (`O(n log n)`, both `O(n)` edits, `index i`).
- Captured the detailed roadmap for resolving the remaining edge cases in `SPAN_VALIDATION_IMPROVEMENT_PLAN.md` (geometry capture, normalized matching, multi-fragment handling, and disambiguating single-character spans).
- Next steps are to execute that plan, re-run PDF creation under app context, and verify all warnings disappear before we declare the rewrite pipeline stable.

## 7a. Latest Updates – 2025-10-03
- Restored span geometry enrichment in `SmartSubstitutionService` via `_build_span_context`, replacing the removed `_build_contexts_from_payload` helper so span lookups succeed again.
- Hardened `BaseRenderer` span matching (`_find_occurrences`, `_fingerprint_matches`) to handle missing char arrays, normalize prefix/suffix comparisons, and keep deterministic ordering.
- Smart Substitution API requests now populate `selection_bbox` / `selection_quads`, so the UI “Add Random Mappings” action saves without raising fallback alerts.
- Regression checks: `backend/.venv/bin/python3.13 -m pytest backend/tests/test_span_overlay_plan.py backend/test_stream_analysis.py -q`.
- Reintroduced `BaseRenderer.build_enhanced_mapping_with_discovery()` so pdf_creation and overlay renderers can reuse structured mapping contexts without the legacy discovery helper.
- Adjusted `_build_span_operator_rewrite()` to slice the span replacement text over the full operator scope, preserving prefix/suffix fragments instead of collapsing to the replacement token.
- Taught `SpanRewriteAccumulator.add_replacement()` to discard overlapping slice requests (preferring the widest coverage) so duplicate contexts cannot strip neighbouring glyphs.
- `_plan_replacements` now trusts geometry-derived spans first; raw text fallback only runs when no glyph path exists, and `_find_match_position_in_combined_text` normalizes ligatures/punctuation so geometry-free contexts still resolve. Title spans are no longer rewritten when question-level replacements are requested.
