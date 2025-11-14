# Context Transfer: FairTestAI LLM Vulnerability Simulator

## Repository Snapshot
- Workspace: `/Users/shivenagarwal/Downloads/fairtestai_-llm-assessment-vulnerability-simulator-main`
- Backend: Flask (Python 3.9) with PyMuPDF + PyPDF2 pipelines for PDF manipulation
- Frontend: React + TypeScript
- Logging: `backend_server.log` (runs under Flask auto-reload during dev)
- Latest run to evaluate: `32edc5f7-29c3-4782-b1e6-b91461b1d4c1`

## Recent Accomplishments
- **Method 1 (redaction + overlay)** now works perfectly: redaction, rewrite, and overlay align; selection/copy returns the manipulated string, and the overlay hides it cleanly (see screenshot `Screenshot 2025-09-29 at 8.58.50 PM.png`).
- UI fixes: rerun button now robust (retry logic + backend fix). Reset keeps the run visible (no more automatic soft delete).

## Current Pain Point (Method 2: content stream rewrite)
- The rewritten PDF (`after_stream_rewrite.pdf`) shows the manipulated substrings drifting; `final.pdf` overlays cover neighboring words. The issue: our reconstruction rewrites the entire `TJ/Tj` operator and changes spacing, so the replacement spans no longer match the original geometry.
- Goal: surgically replace each mapping substring, leaving the rest of the operator untouched, so the manipulated string occupies the same visual footprint and the overlay hides exactly that string.

## Requirements for the Next Session
1. **Understand Span Hierarchy**  
   Determine how deeply we must parse the PDF content stream (operators, kerning arrays, fonts) to isolate the exact substring. Document findings and plan in a new root-level file (e.g. `REWRITE_PLAN.md`) before coding.

2. **Reconstruction Criteria**  
   - Replacement string must appear between the same prefix/suffix characters in text order (extra spaces or line breaks are okay as long as order is preserved).
   - Visual footprint must match the original span so Method 1 overlay covers it perfectly.
   - Keep the replacement as a single contiguous fragment inside the operator; adjust only with two kerning numbers (leading and trailing) if needed.

3. **Artifacts to Inspect**  
   - `backend/app/services/pipeline/enhancement_methods/base_renderer.py`
   - `backend/app/services/pipeline/enhancement_methods/image_overlay_renderer.py`
   - Run artifacts: `backend/data/pipeline_runs/32edc5f7-29c3-4782-b1e6-b91461b1d4c1/`
   - Logs: `backend_server.log` (notably the `kerning plan for replacement` debug entries)

4. **Evidence to Produce**  
   - Rerun pipeline `32edc5f7-29c3-4782-b1e6-b91461b1d4c1` after changes. Compare `after_stream_rewrite.pdf` vs `final.pdf` to confirm overlays align and text selection works.
   - Keep the methodology reproducible for future runs (log metrics or add tests if feasible).

## Status Summary
- Repository contains unsquashed debugging logs and artefacts; treat the working tree as dirty.
- `pyproject` not provided; rely on existing scripts/venv.
- Frontend changes already committed in prior session—the next session focuses on backend rewrite logic.

> Hand this context to the next Codex agent so they can continue with the precise span reconstruction work.
