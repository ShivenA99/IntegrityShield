# Structured Payloads & JSON Contracts

The pipeline mirrors much of its state into JSON files under `backend/data/pipeline_runs/<run-id>/`. These files allow quick inspection without querying the database.

## `structured.json`
- **Owner:** `StructuredDataManager`
- **Produced by:** `smart_reading` → `content_discovery` → `smart_substitution`
- **Schema Highlights:**
  - `document`: metadata about the source PDF (`source_path`, `filename`, page count).
  - `pipeline_metadata`: timestamps, `run_id`, `stages_completed` (list).
  - `question_index`: per-question positioning info (page, stems, options, bounding boxes).
  - `questions`: fused question list with AI enrichments (mirrors DB `question_manipulations`).
  - `ai_questions`: raw AI model outputs before fusion.
  - `character_mappings`: mapping strategy data (may mirror DB entries).

## `artifacts/` Structure

```
backend/data/pipeline_runs/<run-id>/artifacts/
├─ stream_rewrite-overlay/
│  ├─ after_stream_rewrite.pdf
│  ├─ final.pdf
│  ├─ overlays.json (snapshot metadata)
│  └─ snapshots/<page>_<mapping_id>.png
├─ redaction-rewrite-overlay/
│  ├─ after_rewrite.pdf
│  ├─ final.pdf
│  └─ snapshots/…
└─ logs/
   ├─ content_stream_renderer.log (optional)
   └─ validation.json
```

### `overlays.json`
Example keys:
- `page`: zero-based page index
- `rect`: `[x0, y0, x1, y1]` bounding box in PDF coordinates
- `replacement_text`: manipulated string inserted for validation
- `image_path`: path to PNG snapshot used to overlay original appearance

### Snapshot PNGs
- Captured by `ImageOverlayRenderer._capture_original_snapshots`
- Named `<page>_<mapping-id>.png`
- Provide before/after comparison for QA (useful in Developer console).

## Logs & Metrics
- `logs/live.log` (optional) stores raw events if streaming is enabled.
- `metrics.json` can be exported to summarize stage durations and effectiveness.
- `validation.json` records results of renderer validation (pass/fail, error details).

## Developer Notes
- When editing substring mappings, run `SmartSubstitutionService.sync_structured_mappings` to keep `structured.json` accurate.
- Structured data is deep-copied during reruns (see `PipelineConfig` cloning logic). Ensure additions to DB models are mirrored in JSON to keep reruns consistent.

Update this file if new artifacts or JSON structures are added.
