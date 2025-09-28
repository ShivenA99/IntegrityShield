## Working objective
- Produce a manipulated PDF (content stream replacements + visible overlays) reliably for every run, and surface preview/download in the UI.
- Provide live, page-aware developer logs in the UI during all stages, especially PDF creation.


## What the logs show went wrong (evidence-based)
- Backend gating blocked pdf_creation when any question lacked mappings
  - Error observed: Stage 'pdf_creation' failed: PDF creation blocked: All questions must have at least one mapping. (raised in `backend/app/services/pipeline/pdf_creation_service.py`)
  - Outcome: pdf_creation aborted; no renderer logs emitted.
- Frontend build error in `PdfCreationPanel.tsx` broke the panel
  - Syntax error: JSX style "border: '1px solid '#f5c6cb'" → must be "'1px solid #f5c6cb'".
  - Impact: panel render failure; preview/download UI not reachable.
- Developer log stream route is missing
  - Repeated 404s: GET /api/developer/logs/<run_id>/stream
  - UI expects a stream endpoint; only list endpoints exist and work: `/api/developer/<run_id>/logs`, `metrics`, `structured-data`, `system/health`.
- Frequent Vite proxy ECONNREFUSED / ECONNRESET
  - When backend restarts or is down, requests to `/api/...` fail; WS/HMR also logs `ws proxy socket error`.
  - Impact: noisy dev output; UI may appear broken if backend restarts during runs.
- Enhancement methods not always prepared prior to pdf_creation
  - In one run, methods=[], so nothing was rendered. We added an auto-prepare fallback in `pdf_creation_service`, but we need to verify it’s in effect for all code paths and writes the UI-compatible metadata.
- Import alias issues caused temporary frontend faults
  - "Failed to resolve import" for `@components/question-level/EnhancedQuestionViewer` and `@pages/PreviousRuns` appeared while wiring. Ensure files exist and `tsconfig.json` + `vite.config.ts` aliases align.
- HMR invalidation warnings for `PipelineContext`
  - "usePipelineContext export is incompatible" indicates exported symbol shape changed during HMR. Stabilize API to reduce dev friction.


## Highest-priority plan (ordered)
1) Fix PdfCreationPanel render error (P0)
- Correct the inline style in `frontend/src/components/pipeline/PdfCreationPanel.tsx`.
- Acceptance: Panel renders; no vite parser error; UI shows enhanced PDFs when present.

2) Implement developer logs streaming endpoint (P0)
- Add SSE (Server-Sent Events) or WS route at `/api/developer/logs/<run_id>/stream` to match UI expectation.
- Emit stage, page, method, and per-page stats during content_stream and image_overlay.
- Acceptance: Subscribing from DeveloperPanel shows live events without 404; no connection errors while backend is up.

3) Align gating behavior so pdf_creation proceeds when every question has ≥1 mapping (P0)
- Backend: relax the gate in `PdfCreationService` to presence-only (count ≥ 1), not strict validation.
- Frontend: PdfCreationPanel button gating matches presence-only and shows a clear banner if any question is missing mappings.
- Acceptance: After adding at least one mapping per question, resume pdf_creation succeeds and renderers run.

4) Guarantee enhancement methods are prepared and executed (P0)
- Ensure `pdf_creation` auto-prepares methods if none exist, defaulting to `["content_stream_overlay","pymupdf_overlay"]`.
- Persist UI-compatible metadata keys: `{path|file_path, size_bytes|file_size_bytes, created_at}`.
- Acceptance: On first resume to pdf_creation, at least two outputs (or one combined) are written and listed in structured data.

5) Preview + download wiring verification (P1)
- Confirm `/api/files/<run_id>/<filename>` works; ensure filenames are relative to the run dir in structured data.
- In `PdfCreationPanel`, support both `path` and `file_path`, render iframe preview, and provide a download button.
- Acceptance: Preview renders inline; clicking download retrieves a non-empty manipulated PDF.

6) Stabilize frontend module aliases and context exports (P1)
- Ensure `tsconfig.json` and `vite.config.ts` match alias paths for `@components`, `@pages`, `@hooks`, etc.
- Stabilize `PipelineContext` exports to avoid HMR incompatibilities.
- Acceptance: No more import resolution errors or HMR export incompatibility warnings during typical edits.

7) Re-run behavior setting (P1)
- Add a Setting: "Re-run start at" with options: Step 1 (Smart Reading) or Step 3 (Smart Substitution).
- Backend respects selection: if required data for Step 3 is missing, fall back to Step 1 automatically.
- Acceptance: Re-run starts at desired step; if prerequisites are missing, UI shows a notice and the run begins at Step 1.

8) Robust PDF text manipulation coverage (Tj/TJ) and overlay geometry (P2)
- Upgrade content stream handling to 100% coverage:
  - Decompress streams (FlateDecode), preserve operators and arrays.
  - Parse TJ arrays and Tj strings, handling octal escapes, hex strings `<...>`, and font encodings.
  - Consider `pikepdf` for low-level content streams + `pdfminer.six` to build a text span map; perform surgical replacements by xobject/sequence and by glyph ranges.
  - Escape `\`, `(`, `)` in replacements; re-encode to preserve byte lengths where needed.
- Overlay precision:
  - Derive bounding boxes from `pdfminer` LTTextLine/Char; draw opaque mask + replacement glyph image aligned to baseline.
- Metrics to collect per page:
  - tokens_scanned, tj_segments, matches_found, replacements_applied, bytes_in/out delta, overlay_rect_count, overlay_area_pct, pages_with_zero_hits.
- Acceptance: For test PDFs with known strings and mappings, 100% of targets replaced; logs show per-page hit counts > 0 when expected.


## Acceptance test matrix (condensed)
- Gating: With all questions having ≥1 mapping, pdf_creation runs without raising.
- Methods: When none exist, pdf_creation auto-creates content_stream_overlay + pymupdf_overlay; structured data lists outputs with sizes > 0.
- Preview/Download: iframe shows the manipulated PDF; download is a valid PDF; MD5 differs from input when replacements occur.
- Logs: List endpoint returns data; stream endpoint pushes live events during pdf_creation; per-page stats visible.
- Stability: No vite parser/alias/HMR errors during a full run.


## Next actions (immediate)
- [P0] Fix `PdfCreationPanel.tsx` inline style.
- [P0] Add `/api/developer/logs/<run_id>/stream` SSE endpoint and wire DeveloperPanel to it.
- [P0] Relax backend gating in `PdfCreationService` to presence-only.
- [P0] Verify/finish auto-prepare in `pdf_creation_service` and ensure UI-compatible metadata is written.
- [P1] Confirm preview/download and alias/export stability.
- [P2] Plan implementation for full Tj/TJ + overlay precision (likely introduce `pikepdf` + `pdfminer.six`). 
