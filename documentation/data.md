# Data & Storage Guide

The simulator combines relational storage (SQLAlchemy) with filesystem artifacts per run. This document summarises the database schema, structured JSON contracts, and on-disk layout you can expect after running the pipeline and classroom stages.

## Database Schema

Alembic migrations define the canonical schema (`backend/migrations/versions/`). Key tables:

### Core Pipeline Tables

| Table | Purpose | Key Columns |
| --- | --- | --- |
| `pipeline_runs` | One record per run. | `id` (UUID), `original_pdf_path`, `status`, `current_stage`, `pipeline_config` (JSON), `structured_data` (JSON), `processing_stats` (JSON), timestamps. |
| `pipeline_stages` | Per-stage execution metadata. | `pipeline_run_id`, `stage_name`, `status`, `stage_data` (JSON), `duration_ms`, `error_details`, timestamps. |
| `question_manipulations` | Editable question content and mappings. | `pipeline_run_id`, `question_number`, `question_type`, `original_text`, `options_data` (JSON), `substring_mappings` (JSON), `stem_position`, `ai_model_results` (JSON). |
| `ai_model_results` | Effectiveness testing responses. | `pipeline_run_id`, `question_id`, `model_name`, `manipulated_answer`, `was_fooled`, `full_response` (JSON), `tested_at`. |
| `enhanced_pdfs` | Generated PDF artifacts. | `pipeline_run_id`, `method_name`, `file_path`, `generation_config` (JSON), `validation_results` (JSON). |
| `pipeline_logs` | Structured log events. | `pipeline_run_id`, `stage`, `level`, `message`, `context` (JSON), `timestamp`. |
| `performance_metrics` | Custom metrics per stage. | `pipeline_run_id`, `stage`, `metric_name`, `metric_value`, `metric_unit`, `details` (JSON). |
| `character_mappings` | Character substitution metadata. | `pipeline_run_id`, `mapping_strategy`, `character_map` (JSON), `usage_statistics` (JSON). |

### Classroom Tables

| Table | Purpose | Key Columns |
| --- | --- | --- |
| `answer_sheet_runs` | Classroom dataset metadata. | `id`, `pipeline_run_id` (FK), `classroom_key` (slug, unique per run), `classroom_label`, `notes`, `attacked_pdf_method`, `attacked_pdf_path`, `origin`, `status`, `config` (JSON), `summary` (JSON), `total_students`, `artifacts` (JSON), `last_evaluated_at`, timestamps. |
| `answer_sheet_students` | Synthetic student roster. | `id`, `run_id` (FK → `answer_sheet_runs`), `pipeline_run_id`, `student_key`, `display_name`, `is_cheating`, `cheating_strategy`, `copy_fraction`, `paraphrase_style`, `score`, `metadata` (JSON). |
| `answer_sheet_records` | Per-question student answers. | `id`, `run_id`, `student_id`, `pipeline_run_id`, `question_id`, `question_number`, `cheating_source`, `answer_text`, `paraphrased`, `score`, `confidence`, `is_correct`, `metadata` (JSON). |
| `classroom_evaluations` | Aggregated classroom analytics. | `id`, `answer_sheet_run_id`, `pipeline_run_id`, `status`, `summary` (JSON), `artifacts` (JSON), `evaluation_config` (JSON), `completed_at`, timestamps. |

### Configuration

| Table | Purpose |
| --- | --- |
| `system_config` | Arbitrary key/value storage for feature flags or runtime configuration. |

> All JSON columns transparently leverage PostgreSQL `JSONB` when available (see `app/models/pipeline.py` for the `json_type` helper).

## Structured JSON

`StructuredDataManager` mirrors pipeline state to disk in `structured.json` so analysts can inspect runs without DB access. Key sections:

- `document` – Source PDF metadata and manual input references.
- `pipeline_metadata` – Stage completion list, timestamps, configuration snapshot.
- `questions` – Array mirroring `question_manipulations`.
- `question_index` – Geometry info (page, spans, bounding boxes).
- `character_mappings` – Current substitution strategy.
- `ai_questions` – Raw AI model outputs pre-fusion.

Classroom dataset artifacts (`answer_sheets.json`, `answer_sheet_summary.json`) expose:

- `run_id`
- `generated_at`
- `config` snapshot used for simulation
- `summary` (cheating_counts, score stats)
- `students` array with per-student metadata
- Optional `records` in Parquet format when `write_parquet=true`

Evaluation artifacts (`classroom_evaluations/<key>/evaluation.json`) contain:

- `classroom_id`, `classroom_key`, `classroom_label`
- `attacked_pdf_method`
- `evaluated_at`
- `summary` (cheating_rate, strategy_breakdown, score buckets)
- `students` metrics (score, is_cheating, counts)

## Filesystem Layout

```
backend/data/
├─ pipeline_runs/
│  └─ <run-id>/
│     ├─ structured.json
│     ├─ enhanced_<method>.pdf
│     ├─ answer_sheets/<classroom_key>/...
│     ├─ classroom_evaluations/<classroom_key>/evaluation.json
│     └─ artifacts/<method>/...
└─ manual_inputs/
```

Artifacts follow method-specific schemas:

- **Stream Rewrite Overlay** – `artifacts/stream_rewrite-overlay/{overlays.json,snapshots/,after_stream_rewrite.pdf,final.pdf}`
- **Redaction Overlay** – `artifacts/redaction-rewrite-overlay/...`
- **LaTeX Dual Layer** – `artifacts/latex-dual-layer/{latex_dual_layer_attacked.tex, latex_dual_layer_final.pdf, metadata.json}`

## Data Access Tips

- **Run Directory Helper** – Use `backend/app/utils/storage_paths.py` to resolve run-relative paths.
- **Cleanup** – `AnswerSheetGenerationService` and `pipeline_routes.delete_classroom_dataset` remove stale directories before regenerating data.
- **Relative Paths** – All artifact paths returned via API are relative to the run directory to keep browser downloads simple.

## Schema Changes Checklist

1. Create an Alembic migration (`flask db revision --autogenerate -m "describe change"`).
2. Update SQLAlchemy models (`backend/app/models/...`).
3. Reflect changes in structured JSON or dataset artifacts if necessary.
4. Document the update here and in [backend.md](backend.md).
5. Verify `ensure_database_schema()` still succeeds on fresh environments.

Keeping schema documentation current dramatically reduces onboarding time and avoids accidental drift between DB and filesystem contracts.
