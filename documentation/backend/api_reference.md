# Backend API Reference

This document summarizes the REST endpoints exposed to the React SPA (and, by extension, any automation). All routes are rooted at `/api` and return JSON.

## Pipeline Routes (`/api/pipeline`)

| Method & Path | Description | Request Body | Response |
| --- | --- | --- | --- |
| `POST /start` | Upload a new PDF & kick off `smart_reading` → `content_discovery`. | `FormData` with `original_pdf` and optional arrays: `target_stages`, `ai_models`, `enhancement_methods`, `skip_if_exists`, `parallel_processing`, `mapping_strategy`. | `202 Accepted` with `{ run_id, status, config }`. Background thread continues execution. |
| `GET /runs` | Paginated list of runs. Supports search and filtering. | Query params: `q`, `status`, `include_deleted`, `sort_by`, `sort_dir`, `limit`, `offset`. | `{ runs: [...], count, offset, limit }`. Each run row includes status, stage, validation stats. |
| `GET /<run_id>/status` | Snapshot of run state (current stage, status, structured data, metrics). Used for polling UI. | None. | `PipelineRunSummary` JSON (see `frontend/src/services/types/pipeline.ts`). Returns 404 while a new rerun is still being hydrated. |
| `POST /<run_id>/resume/<stage>` | Force execution to restart from the specified stage (useful for reruns). | Empty body. | `200 OK` on success; orchestrator restarts from the requested stage. |
| `POST /<run_id>/continue` | Resume downstream stages (typically `pdf_creation`, `results_generation`) after mappings are ready. |
| `POST /fork` | Clone an existing run to a new ID, copying artifacts and creating a fresh pipeline (e.g., branch experiments). | `{ source_run_id, target_stages? }`. | `202 Accepted` with new `run_id`. |
| `POST /rerun` | Create a rerun. If structured data and questions exist, the rerun starts at `smart_substitution`; otherwise it replays from scratch. | `{ source_run_id, target_stages? }`. | `202 Accepted` with `{ run_id, rerun_from, mode, status }`. Requires brief polling; docs note new status may 404 for a few hundred ms. |
| `POST /<run_id>/soft_delete` | Mark a run as deleted without removing artifacts (sets `processing_stats.deleted=true`). | None. | `{ run_id, deleted: true }`. |
| `DELETE /<run_id>` | Permanently delete run and artifacts. | None. | `204 No Content`. |

### Status Payload Shape (summary)

```json
{
  "run": {
    "id": "…",
    "status": "pending|running|completed|failed",
    "current_stage": "smart_substitution",
    "structured_data": {...},
    "pipeline_config": {...},
    "processing_stats": {...}
  },
  "stages": [
    { "stage_name": "smart_reading", "status": "completed", "duration_ms": 1234, ... },
    ...
  ],
  "questions": [...],
  "metrics": [...],
  "logs": [...]
}
```

Refer to `frontend/src/services/types/pipeline.ts` for the exact TypeScript interfaces consumed by the SPA.

## Question Routes (`/api/questions`)

| Method & Path | Description | Request Body | Response |
| --- | --- | --- | --- |
| `GET /<run_id>` | Retrieve all question manipulations for a run (stem text, options, substring mappings, AI metadata). | None. | Array of `QuestionManipulation` DTOs. |
| `POST /<run_id>/gold/refresh` | Re-sync gold answers/confidence from AI results. | Optional `{ model_name }`. | `{ updated: <count> }`. |
| `PUT /<run_id>/<question_id>/manipulation` | Save edited substring mappings + metadata for a question. Syncs DB and structured JSON. | `{ manipulations: [...], question_type?, options?, stem_text? }`. | Updated question payload. |
| `POST /<run_id>/<question_id>/validate` | Trigger GPT-5 validation on a manipulation. | `{ prompt, temperature?, model? }`. | Validation report JSON. |
| `POST /<run_id>/<question_id>/test` | Run multi-model adversarial test (calls `MultiModelTester`). | `{ models: [...], payload? }`. | `{ results: [...], summary }`. |
| `GET /<run_id>/<question_id>/history` | Change history for a question (audit log). | None. | `{ history: [...] }`. |
| `POST /<run_id>/bulk-save-mappings` | Batch update substring mappings (typically from CSV/import). | `{ mappings: [...] }`. | `{ updated: <count> }`. |

## Supporting Services

- **External AI Client:** `backend/app/services/integration/external_api_client.py` handles outbound calls; make sure API keys are configured in Flask config/env.
- **Validation Services:** GPT-5 validation ensures manipulations meet formatting expectations before render.

## Error Handling

- All endpoints return JSON errors: `{ "error": "message" }` with appropriate HTTP status.
- Validation failures (e.g. missing question) raise `ResourceNotFound`, returning `404`. Stage failures during resume propagate as `500` with reason.
- Rate-limit / upstream AI errors are logged with context (see `backend_server.log`). UI should surface these via the developer console.

Update this document whenever a new endpoint is introduced or request/response shapes change.
