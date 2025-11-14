# Stream Rewrite Matrix Isolation Plan

> **2025-10-10 Rebaseline:** Span overlay masking is deprecated. All production output must come from direct content-stream surgery with deterministic scaling so we never fall back to raster overlays or isolation hacks.

## 1. Objective
Build a deterministic PDF stream rewrite system that replaces only the requested substrings while preserving all untouched content. The solution must keep visual layout identical, guarantee copy/paste order prefix → replacement → suffix, and eliminate overlay/raster fallbacks by ensuring every replacement succeeds in-stream via measured scaling.

## 2. Design Principles
- **State Fidelity:** Never emit text unless we have the exact CTM, text matrix, text state (`Tc`, `Tw`, `Tz`, `Ts`, leading) and font resources captured from the original stream.
- **Font Preservation:** Default to reusing the original font and encoding; introduce a fallback only when absolutely necessary and make that choice explicit.
- **Operator Surgery:** Operate on the original `Tj` / `TJ` commands in place when possible. If isolation is required, create balanced `ET/BT` blocks with explicit matrices, but the expectation is that span-level rewrites succeed inline via scaling.
- **Deterministic Ordering:** Ensure the final stream produces prefix, replacement, and suffix in the same order they appeared originally.
- **Scaling Guarantee:** Measure every replacement against the captured span width and shrink glyphs or adjust `Tz` so the suffix alignment matches the original footprint.
- **No Silent Fallbacks:** Every code path leads to the same deterministic rewrite strategy; failures must raise clear exceptions with actionable metadata rather than delegating to overlays.
- **Testability:** Build the plan so each phase can be validated independently (unit + integration tests, before/after diff tooling).

## 3. Implementation Phases

### Phase A – Instrumentation & Data Capture
1. **Content Stream Walker Refactor**
   - Build a `ContentStateTracker` that processes every operator (`q`, `Q`, `cm`, `BT`, `ET`, `Tm`, `Td`, `TD`, `T*`, `'`, `"`, `Tj`, `TJ`).
   - Track stacks for graphics state (`q/Q`) and text state (nested `BT` blocks) with explicit matrix snapshots.
   - Capture per-operator records containing:
     - Operator index
     - Operator name and operands (raw PyPDF2 objects)
     - Current CTM, text matrix, text line matrix (each as tuples of six floats)
     - Active text state (`Tf` resource name, size, `Tc`, `Tw`, `Tz`, `TL`, `Ts`)
     - Nesting depth (graphics and text)
     - Original operand bytes (for literal vs hex strings)
   - Persist these records so later phases can reference them without re-parsing.

2. **Span Alignment Enhancements**
   - Augment PyMuPDF span extraction to include the 6-parameter matrices for each span.
   - Map spans to operator records by order and normalized text so we can cross-check bounding boxes and widths.

3. **Encoding Detection**
   - For each `Tj`/`TJ`, record whether the text operand is literal (`()`) or hex (`<>`) and the exact byte sequence.
   - For `TJ`, store the interleaved sequence (strings + numbers) so kerning adjustments survive untouched.

### Phase B – Replacement Planning
1. **Augmented Match Context**
   - Extend replacement planning to identify the specific operator record(s) and character offsets that contain the target substring.
   - Support matches that span multiple operators or multiple entries inside a single `TJ` array.

2. **Width & Matrix Metadata**
   - For each match, compute:
     - Prefix matrix (matrix right before the first replacement glyph)
     - Replacement matrix (calculated from prefix matrix + measured prefix advance)
     - Suffix matrix (matrix at the first suffix glyph)
   - Verify the matrices against PyMuPDF span bounding boxes to catch drift early.

3. **Normalized Stream Alignment**
   - Reconcile question-stem offsets (which include natural spacing) with the normalized span text used during operator planning. Project indices through `SpanRecord.normalized_to_raw_indices` so replacements line up with kerning-less glyph runs.
   - Capture glyph-path hints even when PyMuPDF omits explicit spaces by deriving them from span character metadata; persist both raw and normalized bounds on the context.
   - Allow planner segments to allocate additional glyph slots when replacements introduce extra characters, while still reporting the original span footprint for downstream validation.

### Phase C – Operator Surgery Logic
1. **Preserve Planner Context During Rewrite**
   - ✅ `_plan_replacements` records the covering segment/operator indices and `_reconstruct_page_operations` filters `build_replacement_plan` using those hints, preventing the naive substring fallback for repeated tokens (e.g., `RNNs` in run `cbfead67…`).
   - ✅ Added guard rails/logging so we surface cases where planner metadata exists but the fallback would still fire.
   - ✅ Isolation rewrite now rebuilds the original operator form (`TJ` + numeric adjustments) via `_build_isolation_tj_array`, preserving kerning/byte semantics when BT/ET fallbacks fire.

2. **When Replacement Fits Within a Single Operator**
   - **Case `Tj` (literal/hex):**
     - Clone the original operand bytes.
     - Replace the substring in place, preserving encoding (escape sequences or hex pairs).
     - No isolated `BT/ET` needed.
   - **Case `TJ`:**
     - Rebuild the `ArrayObject` by splitting the string fragment that contains the substring into `prefix`, `replacement`, `suffix` entries.
     - Preserve all numeric adjustments before and after the modified fragment.
     - Emit replacement text using the same literal/hex style as the source.
     - If the replacement requires width equalization, prefer inserting extra glyphs in the original font; use a fallback font only when that fails a tolerance check.
     - If planner segments for the match are not contiguous, abort inline surgery and fall back to isolation so multi-match arrays stay deterministic.
     - Permit replacements to introduce additional array entries when the new text is longer than the original fragment; distribute any new kerning adjustments across inserted slots instead of truncating characters.

3. **When Isolation Is Required (matrix drift or cross-operator replacements)**
   - Trim the original operator so it emits only the prefix portion.
   - Insert isolated replacement segment:
     - `ET` to close current text object.
     - `BT` to start clean state.
     - `Tf`, `Tc`, `Tw`, `Tz`, `Ts` restored to the recorded state for the replacement (reusing the source font when possible).
     - `Tm` set from the recorded replacement matrix.
     - Emit replacement string using `_build_isolation_tj_array` to keep `TJ` arrays (and their kerning numbers) when planner metadata demands isolation; fall back to `Tj` only when array reconstruction is not possible.
     - Prefix/suffix segments reuse `_build_isolation_tj_array` only when kerning/byte operands are present so we preserve spacing-sensitive data without reintroducing unnecessary arrays; suffix paths now retain trailing adjustments validated by `test_isolation_suffix_tj_preserves_trailing_kern_values`.
     - `ET` to close.
   - Reopen original context:
     - `BT`
     - Restore text state (font, spacing, scaling, rise, leading) via recorded values so the suffix resumes from its original matrix.
     - `Tm` set to suffix matrix.
     - Emit suffix content using the original operator’s operand data (trimmed to suffix-only).
   - Ensure the graphics state stack depth is unchanged (do not cross `q/Q`).
   - Honor planner-provided isolation hints (e.g., zero-length `TJ` match slices tagged `requires_isolation`) so inline surgery is skipped and placeholder runs can drive deterministic BT/ET insertion.

4. **Cross-Operator Replacements**
   - Handle matches spanning multiple operators by repeating prefix-trim → isolated replacement → suffix-restoration for each operator boundary.
   - Maintain consistent replacement font resource references across inserted blocks (share a lazily-registered fallback font only when needed).

### Phase C2 – Span-Level Stream Rewrite (Current Priority)
1. **Span Detection & Planning**
   - Collect PyMuPDF span identifiers (page, block, line, span index) for every `SubstringMapping`.
   - Build `SpanRewritePlan` entries containing span metadata, original span text, rewritten span text (after applying all mappings that fall inside the span), bounding boxes, matrices, linked mapping IDs, and the span's measured width.
   - Split mappings that cross span boundaries; ensure each plan entry targets exactly one span.

2. **Span-Level Rewrite With Scaling**
   - When reconstructing page operations, swap the entire text operand associated with the span for the rewritten text, preserving literal kinds, fragment boundaries, and numeric adjustments.
   - Measure the replacement width using the span font metrics. If the replacement exceeds the original width, compute `scale_factor = original_width / replacement_width` and emit temporary `Tz` (or adjusted font size) changes around the operator so suffix alignment is preserved without disturbing neighbouring content.
   - Persist the applied scale on the `SpanRewriteEntry` to feed validation and regression tooling.
   - **Gap identified 2025-10-08 (still relevant):** Ensure `_collect_span_rewrite_from_plan` and `_remap_fragments_by_diff` consume planner-provided raw replacement indices and fragment metadata so fragment redistribution is deterministic.

3. **Matrix & State Restoration**
   - Restore original `Tz`, `Tf`, `Tc`, `Tw`, and text matrices immediately after the span operator so downstream content reuses the original text state.
   - For Type0 fonts or rotated CTMs, verify the rewritten operator inherits the recorded matrix instead of synthesising a new `Tm`.

4. **Diagnostics & Artifacts**
   - Extend debug JSON to list spans rewritten, including before/after text, bounding boxes, scale factor, and mapping references.
   - Capture width deltas and any scale applied for regression tracking.

*(Existing char-level isolation plan (Phase C1) remains documented as backlog work once span-level scaling is solid.)*

### Phase D – Resource & Font Management
1. **Fallback Font Strategy**
   - Attempt to reuse the original font and encoding for all replacement glyphs.
   - If width or encoding constraints prevent reuse, lazily register a single shared fallback font (e.g., Helvetica) per page and reuse its resource name.
   - Emit structured logs identifying which replacements relied on the fallback.

2. **Marked Content (Optional)**
   - If `/ActualText` is required, wrap only the replacement block in `BDC/EMC` with minimal properties.
   - Prefix and suffix remain untouched to avoid reader reordering.

### Phase E – Safety Checks & Validation
1. **Matrix Consistency Validation**
   - After rewrite, walk the content stream to confirm that every `ET` we inserted has a matching `BT` and vice versa.
   - Ensure the graphics/text state stacks never underflow.

2. **Width Tolerances**
   - Compare computed advances for prefix and suffix against PyMuPDF span widths; raise if drift exceeds a configurable tolerance (e.g., 0.25 pt).

3. **Extraction Order Regression**
   - Run copy/paste simulations (using PyMuPDF text extraction) before and after to assert the prefix → replacement → suffix order.

4. **Binary Diff Harness**
   - Produce diff reports limited to the operators touched; fail the run if unrelated operators changed.

### Phase F – Testing Matrix
1. **Unit Tests**
   - Parsing: confirm operator records capture literal vs hex strings, numeric arrays, stacks.
   - Surgery: verify substring replacement outputs expected operand sequences for each operator type.

2. **Integration Tests**
   - Simple single-operator replacements (Latin, CJK, RTL, ligatures).
   - Cross-operator replacements (prefix in one operator, suffix in next).
   - Nested `BT` / `q` structures.
   - Pages with no replacements (assert no diff).

3. **Visual Regression Hooks**
   - Optional script generating PNGs for before/after pages to catch visual drift.

### Phase G – LLM Automation & UI Wiring
1. **Auto-Mapping Generation**
   - Provide a GPT-5 powered endpoint that returns suggested substring mappings per question (JSON schema aligned with `substring_mappings`).
   - Integrate with UI controls so operators can request mappings and review/edit them inline before persisting.

2. **Validation Workflow**
   - Surface per-mapping GPT-5 validation (answer deviation scoring) with inline status, confidence, and reasoning.
   - Persist validation metadata on mappings and expose aggregate counts in pipeline panels.

3. **Diagnostics Exposure**
   - Feed span rewrite metrics (scale factors, width deltas, span plans) into the UI so operators can audit span-level edits alongside automated mappings.

## 4. Edge Cases & Considerations
- Mixed encodings within the same `TJ` array (hex + literal).
- Operators that include escape sequences (`\(`, `\)`, `\\`) which must be preserved.
- Ligatures where the match overlaps grapheme clusters; ensure replacements respect font encoding.
- RTL scripts and vertical writing modes (Japanese) where matrices may include negative scaling or rotation.
- Rotated text (non-axis-aligned CTM).
- Suffix-only or prefix-only replacements (one side empty).
- Multiple replacements within the same operator; apply sequentially while updating matrices.
- Graphics state resets between operators (`BT`, `ET`, `q`, `Q` sequences) that must be mirrored.

## 5. Execution Notes
- Implement Phases sequentially to keep the code testable.
- Keep instrumentation code side-effect free so planning routines can be reused for diagnostics.
- Document every transformation with structured logs (run id, page, operator index, prior state, new state).

## 6. Progress Tracker

| Phase | Description | Status |
| ----- | ----------- | ------ |
| A | Instrumentation & Data Capture | Completed |
| B | Replacement Planning Enhancements | In Progress |
| C | Operator Surgery Logic | In Progress |
| D | Resource & Font Management | Not Started |
| E | Safety Checks & Validation | Not Started |
| F | Testing Matrix | Not Started |

## 7. Progress Notes
- 2025-10-10: Overlay masking officially retired. Span rewrite outputs must succeed inline with deterministic scaling; overlay artifacts remain only for historical debugging until removed.
- 2025-10-10: ContentStreamRenderer now serializes span plans with scaling summaries, writes plan JSON artifacts, and `PdfCreationService` exposes `scaled_spans` + plan metrics instead of overlay counts. Mapping contexts attach glyph-path hints to avoid span lookup warnings.
- 2025-10-02: Phase A.1 tracker scaffold implemented (`content_state_tracker.py`) capturing per-operator state; width accumulation still pending.
- 2025-10-02: Phase A.1 tracker updated with text-advance estimation and state mutation; pending integration with precise width resolver.
- 2025-10-02: Phase A.2 span extractor created (`span_extractor.py`) capturing matrices/origins for PyMuPDF spans; validation against operator records pending.
- 2025-10-02: Phase A.3 alignment helper added (`span_alignment.py`) mapping operator text to span slices; requires normalization handling for whitespace/zero-width glyphs.
- 2025-10-02: Phase A instrumentation enriched with per-span character metrics (`SpanRecord.characters`) for precise advance calculations.
- 2025-10-02: Added normalized span text cache for alignment to reduce repeated filtering overhead; still need mixed whitespace reconciliation.
- 2025-10-09: Planner now records raw replacement offsets, per-slice max extents, and operator fragment metadata. Base renderer consumes these fields directly (no difflib), extends slices to recorded limits, and flags overlay fallbacks when slice capacity is exhausted. Tests cover operator 71 tail growth, multi-fragment inserts, and courier scaling capture.
- 2025-10-02: Alignment normalization now collapses consecutive whitespace; remaining TODO is handling ligature grapheme splits.
- 2025-10-02: Ligature-aware grapheme slices captured for spans and alignment now snaps prefix/suffix boundaries to grapheme edges.
- 2025-10-02: Operator advance helper introduced (`operator_metrics.py`) projecting span geometry along writing direction; integration with tracker translation pending.
- 2025-10-02: Stream analysis orchestrator implemented (`stream_analysis.py`) feeding precise advances back into a second tracker pass; remaining work includes suffix matrix validation.
- 2025-10-02: Advance metrics now capture projection bounds and directions; operator records store post-text matrices for future suffix checks.
- 2025-10-02: Matrix validation scaffolding added (world delta vs. span projection); diagnostics now annotate out-of-tolerance advances (ligature handling still TODO).
- 2025-10-02: Base renderer consumes span diagnostics and logs advance warnings per operator; Phase A instrumentation now feeds downstream stages.
- 2025-10-02: Operator records now expose world-space start/end coordinates for suffix validation, and runs inherit those diagnostics.
- 2025-10-02: Suffix matrix drift flagged per operator (stored on `TextRun.suffix_matrix_error`); preparing to close Phase A instrumentation.
- 2025-10-02: Base renderer enforces suffix drift tolerance (0.5pt) and triggers full regeneration fallback when exceeded.
- 2025-10-02: Planner now emits prefix/match/suffix segments with derived matrices, fonts, and widths; next step is to feed plans into rewrite logic.
- 2025-10-02: Base renderer now attaches planner segments to runs (rewrite context + plan segment metadata) and applies segment matrices/fonts for all segments (match uses planner width/font/matrix).
- 2025-10-02: Phase B kickoff—runs now retain per-segment rewrite context (prefix/replacement/suffix offsets) for downstream planning.
- 2025-10-02: Isolation fallback now rebuilds `TJ` arrays via `_build_isolation_tj_array`, preserving intra-match kerning numbers and literal kinds; covered by `test_isolation_tj_preserves_internal_kern_adjustments`.
- 2025-10-02: QA: recreated virtualenv, installed `backend/requirements.txt`, and executed `pytest backend/test_merge_runs_into_content.py -q` plus `pytest backend/test_tj_multi_piece_unit.py -q` (both green).
- 2025-10-02: Prefix isolation paths now rebuild `TJ` arrays only when kerning or byte literals demand it, retaining numeric adjustments on inline prefixes while leaving simple cases as `Tj` (`test_isolation_prefix_tj_reuses_original_kern_values`).
- 2025-10-02: Suffix isolation keeps trailing kerning adjustments and adds regression coverage via `test_isolation_suffix_tj_preserves_trailing_kern_values` (pytest suite rerun alongside `backend/test_tj_multi_piece_unit.py`).
- 2025-10-02: Non-array fallback emits ByteString operands for byte-literal segments so deletions and inline rewrites no longer coerce to text (`test_emit_run_operations_uses_bytestring_for_byte_literal_tj`).
- 2025-10-02: Hex-only isolation fallback now reuses operator matrices when span geometry is unavailable; validated by `backend/test_match_planner.py::test_hex_only_match_segment_uses_record_matrix_when_span_missing_geometry`.
- 2025-10-02: Mixed literal deletions split along literal-kind boundaries so byte/text fragments isolate independently (`backend/test_match_planner.py::test_mixed_literal_deletion_forces_isolation_per_fragment`).
- 2025-10-02: Planner splits multi-span match segments so each inherits span matrices and replacement slices (`backend/test_match_planner.py::test_match_segments_split_when_spans_have_distinct_matrices`).
- 2025-10-02: Post-update `stream_analysis` run on `cbfead67-4428-4e01-aef5-b5566472f2e3` overlay PDF confirms zero suffix drift; span extraction still unavailable on regenerated assets (single page-level fallback warning remains).
- 2025-10-02: Added regression `backend/test_stream_analysis.py::test_stream_analysis_reports_single_warning_when_spans_missing` to guard the page-level fallback when PyMuPDF omits spans.
- 2025-10-02: Span extractor now uses `chars` arrays (ignoring synthetic glyphs) so alignment has reliable geometry even when spans lack inline text.
- 2025-10-02: Stream analysis falls back to partial-prefix matches and limits alignment warnings to a single per page notice.
- 2025-10-03: Synthetic advance metrics cover truncated PyMuPDF spans, clearing the residual alignment warning (regression: `backend/test_stream_analysis.py::test_stream_analysis_synthesizes_metrics_for_unaligned_text`).
- 2025-10-03: Inline `TJ` rewrites inject compensating kern adjustments using measured replacement widths so suffix matrices stay aligned (`backend/test_merge_runs_into_content.py::test_tj_array_inline_rewrite_pads_width_with_kerning`).
- 2025-10-03: Deep-dive on run `de3d91e8-2ed9-404c-9141-b8544414f2a2` revealed truncation of longer replacements (`benefit→demerit`, `50→50999`), planner fallback gaps for kerning-heavy substrings (`the main`), and giant negative kerns that break extraction—inline strategy deemed insufficient.
- 2025-10-03: Updated Phase C plan to mandate char-level isolation per match: capture/restore full text state, use planner matrices for prefix/match/suffix, scale replacement font size or `Tz` inside isolation, and restore suffix `Tm` to eliminate drift.
- 2025-10-03: Type0 font path will reuse `_build_isolation_tj_array` with CID encoding and font width tables; Unicode path emits literal `Tj` with isolation so both encodings share the same scaling/restore logic.
- 2025-10-03: Mapping automation alignment: LLM-generated multi-substring mappings will populate existing `substring_mappings`; renderer changes guarantee deterministic PDF rewrites for arbitrary substrings across Unicode and Type0 fonts.
- 2025-10-05: `_merge_runs_into_content` consumes planner state, width tolerances guard planner fallbacks (pytest coverage on planner spans), and planner-requested fonts are injected into page resources.
- 2025-10-05: Inline `Tj` surgery implemented for full-operator replacements; isolation fallback emits `BT/ET` sequences when planner data diverges (full `TJ` support still pending).
- 2025-10-06: `_parse_tj_array_tokens` and `_rewrite_single_tj_array` now enable inline `TJ` rewrites preserving kerning adjustments and literal/byte encoding while keeping planner widths in tolerance (validated via `test_merge_runs_into_content.py`).
- 2025-10-06: Isolation rewrite path now reapplies planner char/word spacing, scaling, and rise before replacements and restores original matrices after (`test_isolation_restores_state_with_planner_metadata`), paving the way for cross-operator isolation work.
- 2025-10-06: `_apply_replacements_to_runs` now consumes planner segments per-operator, enabling cross-operator replacements with isolation fallbacks and preserving prefix → replacement → suffix order (`test_cross_operator_replacement_uses_isolation_and_preserves_sequence`).
- 2025-10-06: Mixed literal/hex arrays retain byte operands during inline surgery and isolation now preserves byte literals when tolerances force BT/ET fallback (`test_tj_array_inline_rewrite_preserves_byte_literal_segments`, `test_isolation_preserves_byte_literals_when_width_mismatch`, `test_tj_byte_literal_isolation_emits_byte_string`, `test_cross_operator_deletion_removes_segments_and_restores_suffix`).
- 2025-10-07: Planner tags zero-length `TJ` match segments with `requires_isolation`, and BaseRenderer forces isolation using placeholder runs so deletions bypass inline array surgery (`test_tj_deletion_forces_isolation_when_segment_requests_it`).
- 2025-10-07: `_rewrite_single_tj_array` now rejects non-contiguous match spans so multi-match arrays fall back to isolation (`test_tj_array_inline_rewrite_rejects_disjoint_match_segments`).
- 2025-10-07: Manual verification on run `cbfead67-4428-4e01-aef5-b5566472f2e3` confirms zero-length `TJ` deletions emit isolation `BT/ET` sequences (operator 159).
- 2025-10-08: Strategy pivot—introduce span-level rewrite pipeline (`stream_rewrite_overlay_span.pdf`) that rewrites entire spans in the stream while masking them with raster overlays. Char-level isolation remains backlog; focus is on SpanRewritePlan generation, span operand swapping, and overlay painter updates.
- 2025-10-08: `SpanRewriteEntry` now captures per-fragment rewrite diagnostics and the renderer reuses original `TextStringObject`/`ByteStringObject` operands whenever fragments stay unchanged. Replacement text distribution maps onto the original fragment boundaries to preserve ligatures and literal kinds.
- 2025-10-08: Identified normalized-alignment gap—question contexts reference spaced stems while planner operates on collapsed span text. Need to project offsets through `normalized_to_raw_indices`, capture `matched_glyph_path` hints, and allow planner segments to grow when replacements add glyphs before span-level pipeline can be considered complete.
