# Backend Architecture & API

The backend is a Flask application that orchestrates PDF manipulation stages, manages AI integrations, and persists pipeline state. This guide summarises the module layout, pipeline services, database topology, and public API surface.

## Application Composition

| File | Responsibility |
| --- | --- |
| `backend/app/__init__.py` | Application factory (`create_app`), config wiring, extension init, auto-migration on startup. |
| `backend/app/config.py` | Environment variables, defaults (AI models/methods, storage paths, auto migration flag). |
| `backend/app/extensions.py` | SQLAlchemy, Flask-Migrate, CORS, WebSocket (Sock) initialisation. |
| `backend/app/api/` | REST blueprints; `pipeline_routes.py` contains the majority of endpoints. |
| `backend/app/models/` | SQLAlchemy models (pipeline runs, stages, questions, answer sheets, classroom evaluations, etc.). |
| `backend/app/services/` | Domain services organised by concern (pipeline stages, AI clients, data management, developer tooling). |
| `backend/app/utils/` | Logging helpers, filesystem path utilities, time helpers, migration bootstrapper. |

### Auto-Applied Migrations

`ensure_database_schema()` (called during app start) runs `alembic upgrade` when `AUTO_APPLY_DB_MIGRATIONS` is `true`. It gracefully falls back to `db.create_all()` if running against in-memory SQLite (testing) or when migrations are unavailable.

- Alembic scripts live under `backend/migrations/versions/`.
- Key revisions:  
  - `3b8be3ac12de` – introduces `answer_sheet_runs`, `answer_sheet_students`, `answer_sheet_records`.  
  - `7f2b8c19fb8c` – adds classroom metadata columns and `classroom_evaluations`.

Disable automatic upgrades by setting `FAIRTESTAI_AUTO_APPLY_MIGRATIONS=false` in your environment; this is useful for CI gates where you want to control migration application explicitly.

### Database Operations & Migrations

Run these commands from the `backend/` directory with the virtualenv activated:

```bash
# Create a new migration (after editing SQLAlchemy models)
flask db revision --autogenerate -m "short description"

# Apply migrations to the active database
flask db upgrade

# Roll back one revision (use with care)
flask db downgrade -1

# Inspect history / heads
alembic history
alembic current
```

For a clean start against a fresh Postgres container, drop and recreate the database (or remove the Docker container) and run `flask db upgrade` once before launching the app. When auto-migrations remain enabled, `python run.py` will perform the upgrade automatically; manual commands remain useful in CI or staged environments.

> Helpful snippet for CI: `FLASK_APP=app FAIRTESTAI_ENV=production flask db upgrade` ensures migrations run against the configured production database.

## Pipeline Services

Stages run sequentially via `PipelineOrchestrator`:

| Stage Enum | Service | Purpose | Outputs |
| --- | --- | --- | --- |
| `smart_reading` | `SmartReadingService` | OCR + vision extraction, populates `structured.json`. | `structured.json`, AI question drafts. |
| `content_discovery` | `ContentDiscoveryService` | Fuse multi-model outputs, seed `QuestionManipulation`. | DB rows for questions/spans, structured metadata. |
| `smart_substitution` | `SmartSubstitutionService` | Apply adversarial mappings, resolve geometry, sync JSON ↔ DB. | Updated mappings, character map stats. |
| `effectiveness_testing` | `EffectivenessTestingService` | Optional: re-run manipulated content through target models. | `ai_model_results` metrics, cheat detection hints. |
| `document_enhancement` | `DocumentEnhancementService` | Prepare overlay/LaTeX assets, fonts, geometry. | Artifact configs under `artifacts/`. |
| `pdf_creation` | `PdfCreationService` | Render attacked PDFs for each configured method. | `enhanced_pdfs`, `artifacts/<method>/final.pdf`. |
| `results_generation` | `ResultsGenerationService` | Summarise pipeline stats, finalize run status. | `performance_metrics`, status `completed`. |

### Classroom Dataset Lifecycle

Beyond the enumerated stages, the pipeline now supports classroom-level modelling:

1. **Dataset Generation** – `AnswerSheetGenerationService.generate` synthesises student answer sheets once attacked PDFs exist. It writes artifacts under `answer_sheets/<classroom_key>/` and persists `AnswerSheetRun`, `AnswerSheetStudent`, and `AnswerSheetRecord` rows.
2. **Evaluation** – `ClassroomEvaluationService.evaluate` aggregates student metrics (cheating breakdown, score distributions, averages) and saves a `ClassroomEvaluation` record with JSON summary under `classroom_evaluations/<classroom_key>/evaluation.json`.

These services surface through dedicated API endpoints (see below) and power Stage 5/6 in the frontend.

## API Surface (REST)

All routes are rooted at `/api`. Selected highlights:

| Method & Path | Description |
| --- | --- |
| `POST /pipeline/start` | Upload a new PDF (multipart) and kick off the pipeline. Accepts optional JSON config overrides (stages, models, methods). |
| `GET /pipeline/runs` | Search/filter previous runs (`q`, `status`, `limit`, `offset`). |
| `GET /pipeline/<run_id>/status` | Fetch run summary, stage statuses, enhanced PDF metadata, classroom progress. |
| `POST /pipeline/<run_id>/resume/<stage>` | Resume execution from a given stage. |
| `POST /pipeline/<run_id>/continue` | Queue downstream stages based on pending targets. |
| `POST /pipeline/rerun` | Clone a run, preserving mappings and structured data. |
| `DELETE /pipeline/<run_id>` | Permanently delete a run and artifacts. |
| `GET /pipeline/<run_id>/classrooms` | List classroom datasets attached to a run. |
| `POST /pipeline/<run_id>/classrooms` | Generate (or regenerate) a classroom dataset. Payload supports overrides: `{ "classroom": { "classroom_key", "classroom_label", "notes", "attacked_pdf_method" }, "config": { ...generation overrides... } }`. |
| `DELETE /pipeline/<run_id>/classrooms/<classroom_id>` | Remove classroom dataset and associated artifacts. |
| `POST /pipeline/<run_id>/classrooms/<classroom_id>/evaluate` | Run classroom analytics. Optional body: `{ "thresholds": { ... } }` (reserved for future tuning). |
| `GET /pipeline/<run_id>/classrooms/<classroom_id>/evaluation` | Retrieve latest evaluation summary and fetch artifact JSON. |

Questions, mappings, and validation endpoints remain available under `/api/questions/...` and `/api/validation/...` as before. See `pipeline_routes.py` and `questions_routes.py` for full parameter lists.

### Response Highlights

- `GET /pipeline/<run_id>/status` now returns:
  - `enhanced_pdfs` with `has_attacked_pdf` flag only when artifacts exist.
  - `classrooms` array with dataset metadata and evaluation links.
  - `classroom_progress` summarising dataset counts and evaluation completion.
- Classroom routes serialise timestamps in ISO 8601 and include artifact-relative paths (relative to `run_directory`).

## Logging & Metrics

- **Structured Logging** – All services use `get_logger` (`backend/app/utils/logging.py`) to emit contextual logs. Include `run_id`, `stage`, and `component` for easy filtering.
- **Live Streaming** – `live_logging_service` pushes events over WebSocket/SSE to the frontend developer console.
- **Persistent Logs** – `pipeline_logs` table stores historical entries accessible via the API and `developer` panel.
- **Metrics** – Use `record_metric(run_id, stage, metric_name, value, unit)` to capture timings and counts in `performance_metrics`.
- **Artifacts** – Validation logs (`validation.json`) and overlay snapshots live under each run’s `artifacts/` folder.

### Debugging Tips

- Tail server logs: `tail -f backend/dev-server.log` or `backend_server.log`.
- Inspect structured data: `jq '.' data/pipeline_runs/<run>/structured.json`.
- Query classroom tables: `SELECT classroom_label, total_students FROM answer_sheet_runs WHERE pipeline_run_id = '<run>'`.
- Check evaluation artifacts: `cat data/pipeline_runs/<run>/classroom_evaluations/<key>/evaluation.json | jq`.

## Error Handling & Resilience

- Pipeline stages wrap execution in try/except to mark `PipelineStageModel.status` and `PipelineRun.status` appropriately.
- Classroom endpoints surface validation errors with `400` (bad payload) or `404` (missing resources). Server errors return `500` and log context.
- Rerun/resume operations guard against conflicting stage execution by checking current statuses before scheduling.

## Extending the Backend

- **Adding a Stage:** update `PipelineStageEnum`, register the service in `PipelineOrchestrator`, append UI stage definitions, and ensure structured data/logging capture new outputs.
- **New AI Integration:** create a client in `services/ai_clients/`, inject configuration through Flask config, and wrap API calls with retries + cost tracking.
- **Additional Classroom Metrics:** expand `ClassroomEvaluationService._build_summary` and surface new fields in the UI (update TypeScript types).
- **Schema Changes:** create a migration via `flask db revision --autogenerate`, update `data.md`, and verify `ensure_database_schema` still succeeds on fresh environments.
