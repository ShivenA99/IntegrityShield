# Backend Architecture

This backend is a Flask 2.x application organized around pipeline services that manipulate PDFs and maintain state in a relational database (SQLAlchemy ORM). Below is a high-level map of the runtime architecture and code layout.

## Key Modules & Responsibilities

| Path | Purpose |
| --- | --- |
| `backend/app/__init__.py` | Flask application factory, extension registration, blueprint wiring. |
| `backend/app/extensions.py` | SQLAlchemy (`db`), Marshmallow, CORS, and other shared extensions. |
| `backend/app/api/` | REST blueprints. `pipeline_routes.py` is the primary entrypoint for run management. |
| `backend/app/models/` | SQLAlchemy models for runs, stages, questions, AI results, logs, metrics, system config. |
| `backend/app/services/pipeline/` | Stage-specific services (smart reading, content discovery, smart substitution, document enhancement, PDF creation, results generation). |
| `backend/app/services/pipeline/enhancement_methods/` | Rendering techniques (content stream manipulation, image overlays, PyMuPDF fallbacks). |
| `backend/app/services/ai_clients/` | Wrappers for Mistral OCR, OpenAI Vision, GPT-5 fusion, etc. |
| `backend/app/services/developer/` | Live logging, performance monitoring, developer utilities. |
| `backend/app/utils/` | Logging helpers, exception classes, file-path utilities, time helpers. |
| `backend/app/services/data_management/` | Structured data manager, artifact file management. |
| `backend/app/services/pipeline/pipeline_orchestrator.py` | Stage scheduler, background thread runner, pause/resume logic. |

## Request Flow

1. **REST call** (e.g. `POST /api/pipeline/start`) is handled by `pipeline_routes.py`.
2. A `PipelineRun` record is created and the `PipelineOrchestrator` is asked to `start_background` with a `PipelineConfig`.
3. `PipelineOrchestrator` spawns an async event loop on a daemon thread; stages run sequentially as `await service.run(...)` calls.
4. Each stage emits live logs through `live_logging_service`, writes `PipelineStage` status rows, and persists artifacts to `backend/data/pipeline_runs/<run-id>/`.
5. API endpoints poll `GET /api/pipeline/<run-id>/status` to show progress in the UI. Stages can pause (after `content_discovery`) until the user resumes.

## Threading & Async Model

- Flask runs in debug mode with reloader locally; pipeline execution happens in background `threading.Thread` instances.
- Within each thread, the orchestrator drives an asyncio loop, letting stage implementations call async IO (HTTP requests to AI providers, file I/O).
- SQLAlchemy sessions are short-lived per stage; `db.session` commits/rollbacks occur at stage boundaries and error handlers.

## External Integrations

- **AI Providers:** Mistral OCR (`mistral_ocr_client.py`), OpenAI Vision, GPT-5 fusion. Requests use `httpx`, handle 4xx/5xx with retries/logging.
- **PDF Libraries:** PyMuPDF (`fitz`) for geometry, snapshots, and validation; PyPDF2 for parsing and writing content streams.
- **Storage:** Local filesystem structure under `backend/data/`: run artifacts, DB file (`fairtestai.db` for dev), structured JSON caches.

## Configuration

- Environment variables (via Flask config) define API keys, default models, pipeline defaults, logging verbosity.
- `PipelineConfig` captures per-run overrides: target stages, AI models, enhancement methods, etc.
- `SystemConfig` table holds key/value settings (e.g., feature flags) with optional secret flag.

## Error Handling & Resilience

- `PipelineOrchestrator` catches exceptions per stage, marks the stage/run as failed, and records `error_details`.
- API routes surface errors with HTTP 4xx/5xx plus JSON payloads.
- Live logging (`live_logging_service.emit`) pushes structured events for the frontend developer console.

## Deployment Considerations

- Designed to run behind a WSGI server (e.g., Gunicorn) with worker threads enabled.
- Ensure background threads have access to application context (`app.app_context()` is wrapped around runner).
- File storage paths (`backend/data/`) should be persisted/shared if multiple workers are used.
- DB defaults to SQLite for local development; swap to Postgres by adjusting SQLAlchemy URI (JSONB columns already supported).

Keep this document synced when we add new services or modify threading/configuration patterns.
