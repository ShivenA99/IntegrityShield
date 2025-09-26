# FairTestAI Advanced Pipeline – Current Implementation

## Runtime Topology
- **Backend**: Flask 3.x app served via `backend/run.py`. Environment configured through `.env` (`FAIRTESTAI_*` variables) with SQLite database at `backend/data/fairtestai.db` and pipeline artifacts under `backend/data/pipeline_runs/`.
- **Frontend**: React 19 + Vite dev server on port 5173. Communicates with backend REST API (`/api/pipeline`, `/api/questions`, `/api/developer`) and websocket endpoints (`/developer/logs/<run_id>/stream`).
- **Virtualenv**: `backend/.venv` containing all Python dependencies (Flask, SQLAlchemy, PyMuPDF, OpenAI SDKs, etc.).

## Backend Architecture
- **Application Factory**: `app/__init__.py` loads configuration, initializes extensions (SQLAlchemy, Flask-Migrate, Flask-Sock, CORS) and registers API blueprints.
- **Configuration**: `app/config.py` reads environment variables for DB URL, pipeline storage paths, AI provider keys, default models/methods, and log level.
- **Database Models** (SQLAlchemy ORM, `app/models/pipeline.py`):
  - `PipelineRun`: top-level record tracking uploaded PDF, stage status, configs, structured data snapshot, metrics, and errors.
  - `PipelineStage`: per-stage execution status (pending/running/completed/failed) with timing/memory stats.
  - `QuestionManipulation`: per-question manipulations, mappings, AI results, and metadata.
  - `CharacterMapping`, `EnhancedPDF`, `PipelineLog`, `PerformanceMetric`, `AIModelResult`, `SystemConfig` provide supporting state for global mappings, rendered PDFs, logging, metrics, and configuration.

### Pipeline Services (`app/services/pipeline/`)
Each stage service exposes an async `run(run_id, config)` returning structured results:
1. **SmartReadingService**: Uses PyMuPDF to extract text elements, fonts, image assets, populates `structured.json`, and stores assets in pipeline run directory.
2. **ContentDiscoveryService**: Regex heuristics parse extracted text into question objects (number, stem, options) and persist `QuestionManipulation` rows.
3. **AnswerDetectionService**: Applies heuristic (or AI call if keys available) to populate gold answers and confidence per question.
4. **SmartSubstitutionService**: Builds global character map via `UniversalCharacterMapper`, generates substring mappings using `SubstringManipulator`, validates visual fidelity, and stores manipulation metadata.
5. **EffectivenessTestingService**: Runs `MultiModelTester` (simulated or real AI calls) to assess manipulation impact and aggregates success metrics.
6. **DocumentEnhancementService**: Prepares entries for available rendering methods (dual layer, image overlay, font manipulation, content stream).
7. **PdfCreationService**: Dispatches to registered renderers (`enhancement_methods/`) to produce enhanced PDFs; currently dual-layer implementation rewrites content streams to stack invisible+visible text.
8. **ResultsGenerationService**: Summarizes pipeline outcomes (average effectiveness, recommended methods) and stamps completion metadata.

### Orchestration & Utilities
- **PipelineOrchestrator**: Manages asynchronous stage execution, skip-if-exists logic, stage timing metrics, error handling, and log streaming. Background threads started via Flask app context.
- **ResumeService**: Allows restarting a run from a specific stage by resetting stage states.
- **StructuredDataManager**: CRUD operations for `structured.json` per run (written to pipeline directory for debugging and frontend display).
- **FileManager**: Handles PDF uploads and asset persistence.
- **Developer Tools**: `live_logging_service` (streams logs), `performance_monitor` (records metrics), `database_inspector`, `websocket_manager` for future extensions.
- **Integration Utilities**: Placeholder `ExternalAIClient` that will call OpenAI/Anthropic/Gemini when fully wired.

### Logging & Telemetry
- `structlog` + JSON formatting via `app/utils/logging.py` producing structured logs stored in `pipeline_logs` table and streamed to frontend developer console. Performance metrics recorded per stage.

## Frontend Architecture (`frontend/src/`)
- **Contexts**: `PipelineContext`, `DeveloperContext`, `NotificationContext` maintain active run state, developer mode toggling, toast notifications.
- **Hooks**: `usePipeline`, `useQuestions`, `useDeveloperTools`, etc. encapsulate API polling (SWR) and websocket subscriptions.
- **Components**:
  - Pipeline panels (8 stage-specific components) displayed via `PipelineContainer` with interactive progress tracker.
  - Question-level suite (viewer, mapping tables, effectiveness indicator, preview summary) surfaced on Run Detail page.
  - Enhancement previews, developer dashboard panels (logs, structured data, metrics), shared UI elements (notifications, dialogs, file upload).
- **Pages**: Dashboard (pipeline + developer panel), RunDetail, Settings, DeveloperConsole. Layout components provide navigation and shell.
- **Styling**: `styles/global.css` scratches advanced glassmorphism aesthetic; uses CSS for cards, tracker, developer grid.
- **API Clients**: Organized under `services/api/` (pipeline, questions, enhancement, developer). Utilities handle formatting, validation, storage, and error extraction.

## Data Flow Summary
1. **Upload** – client posts PDF -> `/api/pipeline/start`; FileManager saves to pipeline run directory, DB records created, orchestrator triggered asynchronously.
2. **Stage Execution** – orchestrator iterates requested stages, invoking service `run`, updating DB records, writing out `structured.json`, logging status, and recording metrics.
3. **Frontend Polling** – `PipelineContext.refreshStatus` polls `/status`, updates stage list, structured data, and active run metadata. Developer components subscribe to live logs and metrics via websocket + REST.
4. **Question Operations** – UI fetches `/api/questions/<run_id>`, allows updates/testing through `PUT` + `POST` endpoints; backend refreshes mappings, triggers AI tests if requested.
5. **Outputs** – Enhanced PDFs saved under run directory (`enhanced_<method>.pdf`), references surfaced in structured data for download once implemented.

## Developer Workflow
- Start backend: `cd backend && ../backend/.venv/bin/python run.py` (honors `FAIRTESTAI_PORT` for alternate ports).
- Start frontend: `cd frontend && npm run dev` (exposes Vite dev server).
- Logs: `backend_server.log` / `frontend_server.log` or tail database tables via developer console.
- Run directories: `backend/data/pipeline_runs/<run_id>/` contains original PDF, structured data, assets, generated outputs.
- Activity captured in `DEV_LOG.md` for chronological trace, while `DOC_STATUS.md` and `IMPLEMENTATION_PLAN.md` provide high-level status and roadmap.

## Current Feature Coverage
- Full stage orchestration pipeline with simulated AI testing and dual-layer PDF rendering.
- Structured data persisted at each stage, accessible through UI developer tools.
- Frontend UI walking users through eight-stage terminology with developer console supporting log streaming, structured data view, metrics chart (placeholder data), question-level inspection.
- Environment-based configuration enabling API provider integration once keys supplied.

