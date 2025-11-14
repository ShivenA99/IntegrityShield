# Platform Overview

AntiCheatAI simulates adversarial pressure on automated grading systems. The workflow couples PDF manipulation, LLM-powered extraction, and classroom-scale behavioural modelling to surface vulnerabilities an instructor would otherwise miss.

## Core User Journey

1. **Upload Source Material** – Instructor PDF (or manual question set) is uploaded through the dashboard (`frontend/src/components/pipeline/SmartReadingPanel.tsx`).
2. **Automated Pipeline** – The backend orchestrator (`backend/app/services/pipeline/pipeline_orchestrator.py`) runs smart reading → substitution → document enhancement → PDF creation, persisting state to SQL + disk.
3. **Manual Validation** – Analysts tweak mappings, inspect overlays, and re-run effectiveness tests directly from the SPA.
4. **Download PDFs** – Stage 4 renders attacked variants (`artifacts/<method>/final.pdf`, `enhanced_<method>.pdf`) and updates the run bar chips so analysts know when downloads are ready.
5. **Classroom Simulation** – Using the Classroom action, synthetic student answer sheets are generated per attacked PDF (`AnswerSheetGenerationService`) and stored both in the database and as JSON artifacts.
6. **Classroom Evaluation** – The Evaluation action aggregates cheating metrics, score distributions, and strategy breakdowns (`ClassroomEvaluationService`) to understand classroom-level exposure.

## High-Level Architecture

```
┌────────────────────┐        REST / WebSocket         ┌─────────────────────┐
│ React SPA (Vite)   │ <──────────────────────────────> │ Flask API + Orchestrator │
│  - Stage panels    │                                  │  - Pipeline services ───┐ │
│  - Developer tools │                                  │  - AI clients          │ │
└────────────────────┘                                  └────────────────────────│─┘
         │                                                           │
         ▼                                                           ▼
  Local browser storage                                  Filesystem artifacts (run data)
                                                         SQL (Postgres/SQLite via SQLAlchemy)
```

### Backend Pillars

- **Pipeline Services** (`backend/app/services/pipeline/`) encapsulate each stage. They operate under a per-run app context and perform commits at stage boundaries.
- **AI Clients** (`backend/app/services/ai_clients/`) wrap OpenAI Vision, GPT-4o, Mistral OCR, etc., enforcing consistent prompts, retry logic, and cost tracking.
- **Data Management** (`backend/app/services/data_management/`) coordinates `structured.json`, asset storage, and PDF handling.
- **Classroom Modelling** (`AnswerSheetGenerationService`, `ClassroomEvaluationService`) owns synthetic student creation and evaluation analytics.

### Frontend Pillars

- **PipelineContainer** orchestrates stage panels, run summary chips, and Classroom/Evaluation action buttons (`frontend/src/components/pipeline/PipelineContainer.tsx`).
- **Context Providers** in `frontend/src/contexts/` stream run status, developer logs, and UI settings to components.
- **Shared Styles** (`frontend/src/styles/global.css`) deliver the gradient and accent themes, while classroom stages apply a distinct accent tone.
- **Standalone Pages** (`frontend/src/pages/Classrooms.tsx`, `ClassroomEvaluation.tsx`) handle dataset management and analytics outside the core stage carousel.

## Key Features at a Glance

| Feature | Where it lives | Notes |
| --- | --- | --- |
| Background pipeline execution | `PipelineOrchestrator.start_background` | Async thread per run; emits stage logs and performance metrics. |
| Attacked PDF variants | `DocumentEnhancementService`, `PdfCreationService` | Supports stream rewrite overlay, dual-layer LaTeX, PyMuPDF overlays. |
| Selective overlay crops | `LatexAttackService.execute` | Captures per-rectangle PNG overlays and logs summaries for each LaTeX method. |
| Classroom datasets | `/api/pipeline/<run>/classrooms` + `AnswerSheetRun` model | Creates `answer_sheet_runs`, `answer_sheet_students`, and JSON artifacts. |
| Classroom evaluation | `/api/pipeline/<run>/classrooms/<id>/evaluate` | Computes cheating ratios, strategy breakdowns, score distributions. |
| Live developer console | `frontend/src/components/developer` + `/api/developer/logs` | Streams structured logs with contextual metadata. |
| Rerun & resume | `/api/pipeline/rerun`, `/api/pipeline/<run>/resume/<stage>` | Preserve mappings, avoid re-running expensive stages unnecessarily. |

## When to Update This Document

- New stage added, removed, or reordered.
- Additional AI integration introduced or retired.
- Classroom analytics expanded (e.g., new metrics, new artifacts).
- Frontend flow significantly changes (new panels, navigation).
