# Integrity Shield Demo Redesign – System Walkthrough

This document captures the current end-to-end flow of the Integrity Shield (formerly AntiCheatAI) simulator so UI/UX work can leverage the existing behaviour, data contracts, and run artifacts. It covers the backend pipeline, storage layout, and frontend surfaces that need to be reflected in the new demo experience.

---

## 1. End-to-End Flow Overview

1. **Upload / Selection**  
   - User uploads a PDF or selects an existing pipeline run.  
   - Metadata and run scaffolding are created (`pipeline_runs/<run_id>` with PDFs, LaTeX, structured JSON).

2. **Smart Reading (Extraction)**  
   - Data-extraction pipeline reconstructs LaTeX, extracts question spans, and produces AI-generated question objects with provisional gold answers.  
   - Outputs persisted under `pipeline_metadata.data_extraction_outputs` and `structured.json.ai_questions`.

3. **Content Discovery**  
   - `ContentDiscoveryService` aligns extracted questions with DB `QuestionManipulation` rows, initiates gold answer generation (`GoldAnswerGenerationService`), and records stage progress in `structured.json.pipeline_metadata`.

4. **Smart Substitution**  
   - `SmartSubstitutionService` populates renderer metadata, prepares substring mappings per question, and stores manipulation results/overlays.

5. **PDF Creation**  
   - `PdfCreationService` orchestrates configured enhancement methods (dual layer, ICW, font attack, etc.) to generate manipulated PDFs (`enhanced_<method>.pdf`) plus metadata for each `EnhancedPDF` row.

6. **Results & Reporting**  
   - Final assets (attacked PDFs, diagnostics, logs) live under each run folder.  
   - Frontend surfaces pipeline status, downloadable artifacts, and per-question diagnostics.

For the demo, the plan is to fully process two “hero” documents ahead of time, snapshotting their run folders so the UI can replay the experience without long-running jobs.

---

## 2. Backend Components

| Stage | Service / Module | Key Responsibilities | Persisted Data |
|-------|------------------|----------------------|----------------|
| Smart Reading | `backend/app/services/pipeline/smart_reading_service.py` and data-extraction scripts | OCR/Layout extraction, AI question generation | `structured.json.ai_questions`, reconstructed LaTeX/PDF assets |
| Content Discovery | `ContentDiscoveryService` (`backend/app/services/pipeline/content_discovery_service.py`) | Map AI questions to DB rows, invoke gold answer generation, update pipeline metadata | `structured.json.questions`, `manipulation_results`, `pipeline_metadata.gold_generation`, DB `question_manipulation` |
| Gold Answer Generation | `GoldAnswerGenerationService` (`backend/app/services/pipeline/gold_answer_generation_service.py`) | Prompt GPT‑5.1 for gold answers with type-aware schema, normalize and store results | Updates `questions[].gold_answer`, `answer_metadata`, DB columns |
| Smart Substitution | `SmartSubstitutionService` (`backend/app/services/pipeline/smart_substitution_service.py`) | Build substring mappings, compute “true gold” fallback, stage manipulation payloads | `manipulation_results`, artifacts under `run/artifacts/*`, DB mappings |
| PDF Creation | `PdfCreationService` (`backend/app/services/pipeline/pdf_creation_service.py`) | Execute renderers (dual layer, PyMuPDF overlay, ICW, etc.) against enhanced mappings | `EnhancedPDF` rows, files like `enhanced_latex_dual_layer.pdf`, overlay assets |
| Developer / Demo APIs | `backend/app/api/demo_routes.py` | Expose demo endpoints for run selection, PDF retrieval, evaluation summaries | HTTP responses consumed by `frontend-demo` |

**Storage Layout (per run):**

```
backend/data/pipeline_runs/<run_id>/
  structured.json                  # canonical state for frontend
  science_k-12_doc_05.pdf          # source PDF
  science_k-12_doc_05_reconstructed.pdf
  science_k-12_doc_05.tex
  science_k-12_doc_05_assets/
  artifacts/…                      # method-specific outputs
  assets/…                         # overlay crops, fonts, etc.
```

Structured JSON mirrors DB state and is the artifact we will preload for the demo UI.

---

## 3. Frontend (Current Dev UI)

### Core SPA (`frontend/`)

| Screen / Component | File | Current Behaviour |
|--------------------|------|-------------------|
| Header | `frontend/src/components/layout/Header.tsx` | Shows brand (“Integrity Shield”), active run ID, refresh/reset controls. |
| Sidebar | `frontend/src/components/layout/Sidebar.tsx` | Run summary (status chips, stage, downloads, classroom datasets), refresh/reset buttons, collapse toggle, brand icon. |
| Footer | `frontend/src/components/layout/Footer.tsx` | Static copyright string. |
| Pipeline pages | `frontend/src/pages/Pipeline/*` | Stage-specific panels (question lists, manipulation diagnostics, PDF download links). |

### Demo SPA (`frontend-demo/`)

Three-stage wizard intended for live demos:

1. **Vulnerability Stage** – upload/selection, vulnerability overview tables, AI evaluation cards.
2. **Integrity Shield PDF Stage** – displays manipulated PDF iframe, rotating status messages, reference report.
3. **Resources Stage** – summary cards linking to input/attacked PDFs and reports.

Branding strings, CTA buttons, and placeholders now reflect “Integrity Shield”. This app pulls `/api/demo` endpoints and expects run data to already exist.

---

## 4. Database & Persistence

- **Primary DB**: PostgreSQL (or SQLite in dev) via SQLAlchemy models (`backend/app/models`). Core tables:
  - `pipeline_run` – run metadata, config, status.
  - `question_manipulation` – per-question mappings, gold answers, geometry.
  - `enhanced_pdf` – renderer outputs, stats, file paths.
  - Supporting tables for classrooms, evaluations, etc.
- **Structured JSON** is the single source of truth for the frontend; run folders mirror DB state and include a `structured.json` snapshot used by demo APIs to serve cached data.
- **Assets**: Overlays, fonts, attacked PDFs under `artifacts/` and `assets/` directories keyed by method name.

For a pre-recorded demo, we only need the `structured.json`, enhanced PDFs, and key artifacts copied into the UI bundle or hosted behind static endpoints.

---

## 5. Proposed Demo Preparation Workflow

1. **Select Two “Hero” Papers**
   - Upload and run them end-to-end in the existing app.
   - Verify gold answers, manipulation diagnostics, and final PDFs are correct.

2. **Snapshot Artifacts**
   - Copy the entire `backend/data/pipeline_runs/<run_id>` folders for both runs into a versioned location (or S3).  
   - Note the run IDs; the demo UI will reference them directly using demo APIs or a new static JSON loader.

3. **Enable Demo API (Optional)**
   - If using live backend, ensure `backend/app/api/demo_routes.py` can serve the saved runs even when pipeline services are idle.
   - Alternatively, build a thin API that serves the stored `structured.json` plus PDF files without hitting the database.

4. **Design New UI Shell**
   - Replace dev-centric layout (sidebar, multi-step tables) with a pitch-oriented flow:
     - Hero dashboard summarizing both papers.
     - Storyboard-style stages (Before → Integrity Shield overlay → Classroom impact).
     - Highlights for gold answer manipulation, overlays, and detection analytics.
   - Incorporate new branding (logo, typography, color system) and planned assets.

5. **Integrate Saved Data**
   - Load the two `structured.json` snapshots on init and hydrate UI state without making users wait for pipeline runs.
   - Wire buttons to open stored PDFs (`input`, `enhanced_latex_dual_layer`, etc.).

6. **Asset Creation**
   - Commission logos (vector + favicon) and UI illustrations describing the adversarial flow.
   - Prepare background graphics for slides/hero sections that echo the Integrity Shield story.

7. **Demo Runbook**
   - Document the click path (e.g., select Paper A → show vulnerability map → toggle to Paper B → highlight overlay detail).
   - Include fallback steps if an asset fails to load (e.g., have PDFs locally to open manually).

---

## 6. Key Files to Reference

| Component | Path |
|-----------|------|
| Structured data example | `backend/data/pipeline_runs/<run_id>/structured.json` |
| Gold answer service prompt | `backend/app/services/pipeline/gold_answer_generation_service.py` |
| Pipeline orchestrator | `backend/app/services/pipeline/pipeline_orchestrator.py` |
| Demo API routes | `backend/app/api/demo_routes.py` |
| Frontend layout components | `frontend/src/components/layout/*.tsx` |
| Demo SPA | `frontend-demo/src/App.tsx` |

Review these while designing the new experience so you can map every UI element to a real artifact or API response.

---

## 7. Next Steps for the Redesign

1. Finalize brand guidelines (logo, palette, typography).
2. Define target personas and the storytelling arc for the pitch.
3. Create wireframes for the new demo UI referencing the flows above.
4. Decide whether the demo will rely on the existing backend (serving cached runs) or a static data bundle.
5. Once the design is approved, implement the new UI layer, keeping existing APIs intact for minimal backend changes.

With this context, you can confidently overhaul the experience while leveraging the rich pipeline data already produced by Integrity Shield. Save two polished runs, build the new storyboard UI around them, and you’ll have a reliable, interruption-free demo. 
