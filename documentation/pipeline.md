# Pipeline Reference

This guide describes the end-to-end pipeline flow, artifacts created at each step, and how the classroom dataset stages extend the core workflow.

## Stage Timeline

```
smart_reading → content_discovery → smart_substitution
→ effectiveness_testing (optional) → document_enhancement
→ pdf_creation → results_generation
```

Each stage runs inside `PipelineOrchestrator.start_background`, which spins up an asyncio loop on a worker thread. Stage progress is recorded in `pipeline_stages` and mirrored to the frontend via `GET /api/pipeline/<run>/status`.

### Stage Details

| Stage | Service | Inputs | Artifacts / Side Effects |
| --- | --- | --- | --- |
| smart_reading | `SmartReadingService` | Uploaded PDF (`original_pdf_path`), AI credentials | `structured.json` (raw extraction), `ai_questions` dumps, live logs. |
| content_discovery | `ContentDiscoveryService` | Structured JSON, AI outputs | `question_manipulations`, `structured.json` enriched with geometry, pipeline metadata. |
| smart_substitution | `SmartSubstitutionService` | Fused questions, mapping strategy | Updated substring mappings, `character_mappings`, geometry validation logs. |
| effectiveness_testing | `EffectivenessTestingService` | Manipulated questions, target model list | `ai_model_results`, cheating rate analytics (optional stage). |
| document_enhancement | `DocumentEnhancementService` | Questions + mappings + structured data | Prepares overlay assets (`artifacts/<method>/overlays.json`, snapshots). |
| pdf_creation | `PdfCreationService` | Enhancement assets, config | Renders attacked PDFs (`artifacts/<method>/final.pdf`), updates `enhanced_pdfs` table, validation logs. |
| results_generation | `ResultsGenerationService` | Previous stage outputs | Summary metrics, finalises run status, updates `processing_stats`. |

### Stage Pausing

- The pipeline pauses after `smart_substitution` so analysts can tweak mappings.
- Resuming via UI or `POST /api/pipeline/<run>/resume/document_enhancement` queues downstream stages.
- Buttons in the UI automatically disable once an action completes (e.g., Smart Reading start, Create PDFs) to prevent double submissions.

## Artifacts & Storage Layout

```
backend/data/pipeline_runs/<run-id>/
├─ structured.json
├─ enhanced_<method>.pdf
├─ answer_sheets/                # Populated after classroom dataset generation
│  └─ <classroom_key>/
│     ├─ answer_sheets.json
│     ├─ answer_sheet_summary.json
│     └─ answer_sheets.parquet   # optional, requires pandas
├─ classroom_evaluations/
│  └─ <classroom_key>/evaluation.json
└─ artifacts/
   ├─ stream_rewrite-overlay/
   ├─ redaction-rewrite-overlay/
   └─ latex-dual-layer/
```

Key JSON contracts are documented in [data.md](data.md).

## Classroom Dataset Stage (Stage 5 UI)

After attacked PDFs exist, Stage 5 allows analysts to generate one or more classroom datasets:

1. **Trigger** – `POST /api/pipeline/<run>/classrooms` with an optional payload:
   ```json
   {
     "classroom": {
       "classroom_label": "Section A",
       "notes": "Midterm spoof",
       "attacked_pdf_method": "latex_dual_layer"
     },
     "config": {
       "total_students": 120,
       "cheating_rate": 0.4,
       "cheating_breakdown": { "llm": 0.7, "peer": 0.3 },
       "random_seed": "section-a-midterm"
     }
   }
   ```
2. **Generation** – `AnswerSheetGenerationService` validates prerequisites (enhanced PDFs exist, required stages complete) then:
   - Creates/updates an `AnswerSheetRun`.
   - Synthesises `AnswerSheetStudent` + `AnswerSheetRecord` rows.
   - Writes JSON (and optional Parquet) artifacts under `answer_sheets/<classroom_key>/`.
3. **Status Update** – `GET /api/pipeline/<run>/status` reflects new datasets in `classrooms` with summary stats, artifact pointers, and evaluation status.

### Re-generation

- Passing an existing `classroom_key` or `id` overwrites the previous dataset (old artifacts are removed before writing new ones).
- Each dataset tracks `origin` (`generated` vs `imported`) to support future upload flows.

## Classroom Evaluation Stage (Stage 6 UI)

Evaluation analyses the synthetic classroom to surface cheating insights.

1. **Trigger** – `POST /api/pipeline/<run>/classrooms/<dataset_id>/evaluate` (empty body is fine for defaults).
2. **Processing** – `ClassroomEvaluationService` aggregates per-student metrics:
   - Cheating strategy breakdown (`llm`, `peer`, `fair`).
   - Score statistics (average, median, distribution buckets).
   - Confidence averages (if available).
3. **Persistence** – Results stored in `classroom_evaluations` table and JSON artifact under `classroom_evaluations/<classroom_key>/evaluation.json`.
4. **UI Output** – Stage 6 panel renders summary cards, charts, and tables. Evaluate button disables while processing and re-enables once complete.

### Error Handling

- Missing dataset triggers `404`.
- Empty classroom (no students) returns `400` with guidance to regenerate dataset.
- Server errors surface a generic `500` and log context in `backend_server.log`.

## Failure Modes & Recovery

| Failure | Symptoms | Recovery |
| --- | --- | --- |
| Stage fails (e.g., PDF creation) | Stage badge turns red, run marked `failed` | Inspect `pipeline_logs`, fix issue, rerun from failed stage via `/resume/<stage>`. |
| Dataset generation fails | UI toast + button re-enabled, `500` error | Check backend logs for missing PDFs or invalid config; ensure stage 4 completed. |
| Evaluation fails | Evaluation card shows error toast | Confirm dataset has students and artifacts. Re-run dataset if necessary. |
| Auto-migration fails on startup | Stack trace referencing Alembic | Apply migrations manually (`flask db upgrade`) or inspect DB permissions. |

## Best Practices

- **Lock Buttons** – Frontend automatically disables buttons after actions; adhere to this pattern when adding new controls.
- **Maintain Structured JSON** – If you add new fields to DB models, mirror them in `StructuredDataManager` and dataset artifacts for consistency.
- **Test Pipelines** – Use `scripts/test_fresh_run_api.py` or manual uploads to ensure new changes don’t break the stage chain.
- **Document Changes** – Update [backend.md](backend.md), [frontend.md](frontend.md), or this file when modifying stage flow or classroom logic.
