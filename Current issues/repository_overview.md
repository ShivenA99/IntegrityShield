# FairTestAI Manipulation Simulator — Repository Overview

This reference consolidates architectural notes, feature inventory, and dataflow descriptions for the FairTestAI pipeline (backend Flask + frontend React). It also explains where large language models are used, how PDF manipulations are executed, and how the legacy experiments relate to the current codebase.

---

## 1. High-level Architecture

| Layer | Technology | Responsibilities |
| ----- | ---------- | ---------------- |
| Frontend | React (Vite), TypeScript | Upload PDFs, collect substring mappings, show run progress, developer tooling, preview generated PDFs. |
| Backend API | Flask, SQLAlchemy | Orchestrates the multi-stage pipeline, stores run metadata, exposes REST endpoints (`/api/pipeline`, `/api/questions`, `/api/developer`). |
| Background Pipeline | Async (thread + asyncio) pipeline orchestrator | Executes stages sequentially (`smart_reading` → … → `results_generation`), pauses after content discovery to collect mappings, resumes on demand. |
| Persistence | SQLite (default) | Tables for `pipeline_runs`, `pipeline_stages`, `question_manipulations`, `enhanced_pdfs`, developer logs. Each run also writes structured JSON under `backend/data/pipeline_runs/<run_id>/`. |
| Renderers | PyMuPDF, PyPDF2 (legacy), Pillow | Implement PDF rewrite strategies (`content_stream_overlay`, `pymupdf_overlay`, `image_overlay`, etc.) |

### Repository layout highlights

- `backend/app/services/pipeline/` — Stage services and orchestrator. Key files:
  - `pipeline_orchestrator.py`: background runner, pause/resume logic.
  - `smart_reading_service.py`, `content_discovery_service.py`, etc.: stage-specific workers. Many tap LLMs for extraction or answer simulation.
  - `pdf_creation_service.py`: coordinates renderers, writes `structured.json` stats, logs overlay metrics.
- `backend/app/services/pipeline/enhancement_methods/` — Renderer implementations (content stream rewrite, PyMuPDF overlay, font manipulation, etc.).
- `backend/app/api/` — REST endpoints (pipeline start/continue, question CRUD, developer data).
- `frontend/src/components/pipeline/` — Stage panels, including Smart Reading upload flow, Smart Substitution editor, PDF preview screen. `PipelineContainer` drives stage navigation based on backend status.
- `frontend/src/components/developer/` — Live log viewer, metrics, structured data explorer for developer/debug mode.
- `frontend/src/styles/` — Global styling, dark/light theming.
- `legacy/` and `legacy working manipulations/` — Earlier prototypes for glyph-level attacks, transformation guides, SQL schema notes.

---

## 2. Pipeline Stages and Data Flow

1. **Smart Reading**
   - Upload PDF (`/api/pipeline/start`).
   - Stage service extracts pages via OCR/LLM combos and seeds `structured.json` (questions empty at this stage).

2. **Content Discovery**
   - Runs multi-model extraction (vision models, OCR) to populate `structured.json["questions"]` with stems, options, positional metadata (`positioning.bbox`).
   - Marks `pipeline_runs.status = paused_for_mapping` so the UI can collect substring mappings.

3. **Smart Substitution** (Paused until resume)
   - Users provide substring mappings (`/api/questions/<run>/<id>/manipulation`).
   - Service normalizes mappings, calls LLM validators (GPT-5 service stubbed) to assess plausibility, updates `question_manipulations.substring_mappings` in DB.

4. **Effectiveness Testing** *(optional — often skipped in current runs)*
   - Would simulate answer quality using manipulated stems.

5. **Document Enhancement**
   - Prepares `enhanced_pdfs` rows for the requested renderer methods (defaults are set in `config.py`, currently `dual_layer,image_overlay,font_manipulation,content_stream,pymupdf_overlay`).

6. **PDF Creation**
   - Builds enhanced mapping via `BaseRenderer.build_enhanced_mapping_with_discovery()` (adds discovery tokens for coverage).
   - Invokes renderers in order (content stream overlay → PyMuPDF overlay → others).
   - Writes metrics and debug info to `structured.json`.

7. **Results Generation**
   - Computes summary stats (question count, average effectiveness) and stores them both in `structured.json` and in `pipeline_runs.processing_stats`.

### Data trail per run
- `backend/data/pipeline_runs/<run_id>/demo_paper.pdf` — original upload copy.
- `backend/data/pipeline_runs/<run_id>/structured.json` — canonical structured data, updated after every stage.
- `backend/data/pipeline_runs/<run_id>/enhanced_*.pdf` — renderer outputs.
- `backend/data/pipeline_runs/<run_id>/pipeline_logs.json` *(if developer logging enabled)* — live events emitted via `live_logging_service`.

---

## 3. Renderer internals (current focus)

- **ContentStreamRenderer**
  - Uses PyMuPDF to rewrite text according to mapping, then layers original imagery via `ImageOverlayRenderer` so the final PDF preserves layout while selectable text is manipulated.
  - Tracks `replacements`, `overlay_applied`, `typography_scaled_segments` metrics.

- **PyMuPDFRenderer**
  - Redacts original spans, inserts replacement text using Helvetica, adjusts font size to fit bounding boxes, and overlays snapshots similar to above.
  - Contains question-aware fallback that pulls bounding boxes from `structured.json["question_index"]` when `search_for` misses.

- **ImageOverlayRenderer**
  - Captures raster images for each mapping region, inserts them into the rewritten PDF, and optionally injects invisible text to ensure the text layer matches.
  - Has legacy fallbacks for word-level overlays and question-level bounding boxes.

- **Other renderers** (dual-layer, font-manipulation) remain from earlier experiments (pikepdf-based glyph substitution, etc.) and are mostly for reference/backwards compatibility.

---

## 4. Frontend Features

- **Smart Reading panel** — upload PDF, choose pipeline stop stage, preview PDF inline.
- **Smart Substitution panel** — displays extracted questions, supports substring selection + replacement, validation, random mapping helper (currently auto-resumes — needs decoupling). Added “Auto-map full stem” helper button for quick blanket mappings.
- **PDF Creation panel** — lists generated PDFs, shows download buttons, visual diff placeholders.
- **Developer Console** — real-time logs (`/api/developer/logs/<run_id>`), metrics, structured data viewer, DB inspector.
- **Notification system** — toast alerts for pipeline start/resume errors.
- **Routing** — `Dashboard` (active run), `PreviousRuns`, `Settings`, `Developer` pages, plus dark/light theming.

---

## 5. LLM Usage

| Stage | Purpose | Models (configurable) |
| ----- | ------- | --------------------- |
| Content Discovery | OCR + vision-based question extraction, bounding boxes, metadata. | Defaults to `gpt-4o-mini`, `claude-3-5-sonnet`, `gemini-1.5-pro`. |
| Smart Substitution | Computing “true gold” answers, validating substitutions (via GPT-5 stub). | Configurable via settings; `GPT5ValidationService` orchestrates comparisons. |
| Effectiveness Testing | (Optional) Compare manipulated question outcomes using multi-model simulation. | Same model list as above. |

LLM calls are abstracted through `ExternalAIClient` and `MultiModelTester`. API keys are read from environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_AI_KEY`).

---

## 6. Legacy Projects & Differences

- **`legacy/` directory** — Contains previous iterations of the manipulation tooling (e.g., `attacked_*` PDFs, transformation guide). These experiments focused on glyph substitutions, font-level attacks, and SQL schema prototypes.
- **`legacy working manipulations/`** — Detailed documentation (`FAIRTESTAI_TRANSFORMATION_GUIDE.md`) explaining early database schema, manipulation methods, and renderer pseudocode. Useful for historical context but superseded by the current pipeline modules.
- The new pipeline centralizes logic in services, uses structured JSON for state, and couples renderers tightly with PyMuPDF for rewrite + overlay. Legacy approaches leaned on PyPDF2 and lower-level glyph editing without strong developer instrumentation.

---

## 7. Data Access Patterns

1. Frontend fetches status (`GET /api/pipeline/<run_id>/status`) every few seconds via `usePipeline` hook.
2. Question list (`GET /api/questions/<run_id>`) populates Smart Substitution.
3. Mappings saved via `PUT /api/questions/<run_id>/<question_id>/manipulation`.
4. Pipeline resume triggered with `POST /api/pipeline/<run_id>/continue`.
5. Developer tools poll `/api/developer/...` endpoints for structured data, health checks, and live logs.

`StructuredDataManager` handles JSON load/save; direct DB interactions reside in SQLAlchemy models for persistent stage status.

---

## 8. Known Gaps (as of 27 Sep 2025)

- Renderer text layer fidelity inconsistent (see `issues_report.md`).
- Smart Substitution UI helper auto-resumes pipeline unexpectedly; needs separation between mapping helpers and continuation CTA.
- Developer log streaming is exposed (SSE), but UI lacks error handling when backend restarts.
- Several PDFs (forms, quizzes) yield minimal stems; discovery pipeline requires table/list extraction to support them.
- Tests are manual; no automated regression around PDF outputs or overlay metrics.

---

This reference should serve as a jumping-off point for onboarding, debugging, and planning future fixes.
