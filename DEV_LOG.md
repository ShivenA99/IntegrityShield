# Development Activity Log

- 2025-09-25 23:13:13 MST — Created fresh environment configuration `.env`, documented project status in `DOC_STATUS.md`, and initialized ongoing development log.
- 2025-09-25 23:14:00 MST — Created Python virtual environment at `backend/.venv`. Attempted to upgrade pip and install backend requirements; installs failed due to restricted network access (unable to reach Python package indices).
- 2025-09-25 23:15:05 MST — Documented dependency blockage in `DOC_STATUS.md` and updated outstanding tasks accordingly.
- 2025-09-25 23:18:32 MST — Network access enabled; upgraded pip to 25.2 and successfully installed backend requirements into `backend/.venv`.
- 2025-09-25 23:19:40 MST — Adjusted SQLAlchemy models for Python 3.9 compatibility, created `backend/data/`, and initialized SQLite schema.
- 2025-09-25 23:20:15 MST — Reworked structured data viewer to avoid outdated React dependencies and completed `npm install` in `frontend/`.
- 2025-09-25 23:21:05 MST — Copied environment configuration into `backend/.env`, ensured pipeline data directories exist, and launched backend (`run.py`, PID 29767 -> `backend_server.log`) and frontend dev server (`npm run dev`, PID 29779 -> `frontend_server.log`).
- 2025-09-25 23:22:10 MST — Fixed SQLAlchemy relationships for compatibility and relaunched backend (`run.py`, PID 30332 -> `backend_server.log`).
- 2025-09-25 23:23:00 MST — Updated configuration to use absolute SQLite paths, refreshed `.env`, and relaunched backend (`run.py`, PID 30775 -> `backend_server.log`).
- 2025-09-25 23:26:40 MST — Authored detailed implementation and remaining-work documentation under `docs/`.

## 2025-09-26 — Checkpoint: Overlay-first, manual smart substitution flow

Scope
- End-to-end pipeline focused on image overlay method only.
- Manual substring mapping selection in UI; proceed is gated until all questions have validated mappings.
- Auto-advance: smart_reading → content_discovery → smart_substitution; answer_detection stage removed.

Frontend
- Removed `answer_detection` panel/tab from `PipelineContainer` and `ProgressTracker`.
- Smart Substitution page now renders per-question editors with:
  - Click-drag on stem to add substring mappings with start/end indices.
  - Non-overlap validation, save, and per-question validation call.
  - Shows GPT‑5 gold answer per question (when available).
  - Proceed button enabled only when every question has at least one mapping; advances to PDF creation.
- PDF creation panel lists generated files with download links and an Evaluate button stub.

Backend
- Orchestrator sets `run.current_stage` at stage start for UI auto-navigation.
- Removed `answer_detection` stage from pipeline order.
- Smart Substitution service:
  - No longer auto-generates word-level mappings; UI drives mappings.
  - Computes per-question true gold answers on entry (heuristic fallback if AI not configured).
  - Writes manipulation metadata to structured data; avoids bulk UPDATE for mappings.
- Questions API: added `POST /api/questions/<run_id>/gold/refresh` to recompute gold answers.

Known Issues
- Smart Substitution stage error: `Attribute 'substring_mappings' does not accept objects of type <class 'list'>`.
  - Triggered when assigning `[]` to `question_model.substring_mappings` on some runs due to legacy type binding.
  - Plan: never assign a fresh list at stage entry; only mutate in place or leave `None` until UI saves. Add normalization in the update endpoint using direct UPDATE + `expire` if the existing value is dict-bound.
- UI validation flow: per-question Validate works, but we still need to render the resulting validation status inline and gate proceed strictly on `validated=true` entries.
- PDF preview pipeline exists; evaluation button is a stub pending integration with effectiveness testing stage.

Next Steps
1. Fix `substring_mappings` initialization: remove any assignment to `[]` during stage entry; add type normalization in questions update endpoint.
2. Ensure gold answer is shown per question after Smart Substitution entry; add a quick refresh on panel mount.
3. Gate proceed on validated mappings (not just presence). Display validation badges per mapping.
4. Wire PDF preview to the first available overlay artifact and provide quick download.
