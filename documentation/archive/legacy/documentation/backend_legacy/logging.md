# Logging & Telemetry

The backend uses structured logging and live streaming to help developers debug pipeline runs in real time.

## Logging Stack

- **`get_logger`** (`backend/app/utils/logging.py`): wraps Python logging with structured context. All services call `get_logger(__name__)`.
- **Live Logging Service** (`backend/app/services/developer/live_logging_service.py`): Pushes events `{ run_id, channel, level, message, context }` to connected SSE/WebSocket clients (the frontend developer console subscribes via `/api/developer/logs`).
- **Werkzeug Access Logs:** Displayed in `backend_server.log`; useful for tracing API calls during development.
- **Stage Logs:** Each stage records at least `INFO` start/complete messages, plus `ERROR` on failure. These are saved to the `pipeline_logs` table and visible in the UI.

## Log Channels

| Channel | Source | Example Messages |
| --- | --- | --- |
| `pipeline` | Orchestrator | Stage transitions, pipeline completion/failure. |
| Stage Names (`smart_reading`, `pdf_creation`, …) | Stage services | Per-stage start/completion, contextual metrics (e.g., `kerning plan for replacement`). |
| `pdf_creation` → renderer components | `ContentStreamRenderer`, `PyMuPDFRenderer`, `ImageOverlayRenderer` | Validation results, overlay capture counts, error stacks. |
| `ai_clients` | Mistral/OAI wrappers | Upstream HTTP responses, 4xx/5xx retries. |
| `developer` | Tools like performance monitor, storage inspector | Debug metrics, manual triggers. |

## Standard Log Fields

- `run_id`: Always include when log ties to a pipeline run.
- `stage`: Stage name (if relevant) to ease filtering.
- `component`: Name of service/emitter (e.g., `ContentStreamRenderer`).
- `context`: JSON dict containing structured data (counts, durations, file paths).
- `timestamp`: UTC, auto-populated in DB logs.

## Accessing Logs

1. **Frontend Developer Tools** – open the Dev Tools panel (see frontend docs) to live-stream emitted logs.
2. **Database Queries** – run `SELECT * FROM pipeline_logs WHERE pipeline_run_id = ? ORDER BY timestamp;` for historical analysis.
3. **Server Console** – monitor `backend_server.log` (includes Flask reloader messages, HTTP traces, and Python stack traces on errors).

## Logging Etiquette

- When emitting logs from new code, always include `run_id` and relevant identifiers (e.g., `q_number`).
- Use `context` (dict) rather than embedding long JSON strings in the message.
- For recoverable errors, log at `WARNING` and include enough detail to reproduce.
- For fatal stage errors, log at `ERROR`, store `error_details` on the stage/run, and let the orchestrator mark the run failed.

## Metrics

- `record_metric(run_id, stage, metric_name, value, unit)` writes to `performance_metrics` and emits a live log. Typical metrics: stage durations, change counts, API timings.
- Ensure new metrics include a `metric_unit` (e.g., `ms`, `count`).

Keep this file updated if logging destinations or formats change (e.g., switching to structured JSON logs or adding OpenTelemetry).
