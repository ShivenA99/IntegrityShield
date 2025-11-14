# Database Schema

The backend uses SQLAlchemy with a flexible JSON column configuration (SQLite locally, Postgres-ready). Below is a summary of the core tables.

## ER Diagram (Textual)

```
PipelineRun 1 ── * PipelineStage
PipelineRun 1 ── * QuestionManipulation 1 ── * AIModelResult
PipelineRun 1 ── * EnhancedPDF
PipelineRun 1 ── * PipelineLog
PipelineRun 1 ── * PerformanceMetric
PipelineRun 1 ── * CharacterMapping
```

## Tables

### `pipeline_runs`
- `id` (UUID, PK)
- `original_pdf_path`, `original_filename`
- `current_stage`, `status`
- `structured_data` (JSON) — mirror of `structured.json` on disk.
- `pipeline_config` (JSON) — run-specific configuration (target stages, models, enhancement methods).
- `processing_stats` (JSON) — runtime metadata (e.g., `deleted` flag, size metrics).
- `error_details`, `completed_at`, timestamps.

### `pipeline_stages`
Tracks per-stage execution details.
- `pipeline_run_id` (FK)
- `stage_name`, `status`, `stage_data` (JSON), `duration_ms`, `memory_usage_mb`
- `error_details`, `started_at`, `completed_at`

### `question_manipulations`
Stored question text + substring mappings.
- `pipeline_run_id` (FK)
- `question_number`, `question_type`, `original_text`
- `stem_position` (JSON bounding boxes/quads)
- `options_data` (JSON map of answer choices)
- `substring_mappings` (array of `{ original, replacement, selection_bbox, selection_quads, prefix/suffix }`)
- `manipulation_method`, `effectiveness_score`
- `ai_model_results` (embedded metadata)
- `visual_elements` (optional list of overlay assets)

### `ai_model_results`
Results of adversarial testing.
- `pipeline_run_id`, `question_id` (FK)
- `model_name`, `original_answer`, `manipulated_answer`
- `was_fooled`, `response_time_ms`, `api_cost_cents`
- `full_response` (JSON transcript)
- `tested_at`

### `enhanced_pdfs`
Inventory of generated PDFs.
- `pipeline_run_id`
- `method_name` (e.g., `stream_rewrite-overlay`)
- `file_path`, `file_size_bytes`
- `generation_config`, `effectiveness_stats`, `validation_results`

### `pipeline_logs`
Structured log events surfaced in the UI.
- `pipeline_run_id`
- `stage`, `level`, `message`, `context` (JSON), `component`
- `timestamp`

### `performance_metrics`
Custom metrics recorded during pipeline execution.
- `pipeline_run_id`
- `stage`, `metric_name`, `metric_value`, `metric_unit`
- `details` (JSON)

### `character_mappings`
Stores mapping strategies for text replacement.
- `pipeline_run_id`
- `mapping_strategy`, `character_map`, `usage_statistics`, `effectiveness_metrics`, `generation_config`

### `system_config`
Key/value store for runtime configuration and flags.
- `config_key`, `config_value` (JSON), `description`, `is_secret`

## Migration Notes

- SQLAlchemy uses `JSON` with a PostgreSQL `JSONB` variant for compatibility.
- Alembic migrations (if any) should live under `backend/migrations/` (not present yet; create when schema evolves).
- When running under Postgres, ensure the connection URI is set and run `db.create_all()` or Alembic migrations.

Keep this document updated when new tables or columns are added.
