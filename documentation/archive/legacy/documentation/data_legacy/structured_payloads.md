# Structured Payloads & JSON Contracts

The pipeline mirrors much of its state into JSON files under `backend/data/pipeline_runs/<run-id>/`. These files allow quick inspection without querying the database.

## `structured.json`
- **Owner:** `StructuredDataManager`
- **Produced by:** `smart_reading` → `content_discovery` → `smart_substitution`
- **Schema Highlights:**
  - `document`: metadata about the source PDF (`source_path`, `filename`, `latex_path`, page/mark totals, and `source_files` when manual input is used).
  - `pipeline_metadata`: timestamps, `run_id`, `stages_completed` (list).
  - `question_index`: per-question positioning info (page, stems, options, bounding boxes).
  - `questions`: fused question list with AI enrichments (mirrors DB `question_manipulations`).
  - `ai_questions`: raw AI model outputs before fusion.
  - `character_mappings`: mapping strategy data (may mirror DB entries).
  - `manual_input`: canonical snapshot of manual seed sources (`pdf_path`, `tex_path`, `json_path`, `pipeline_pdf_path`, `source_paths`) plus original JSON metadata for traceability.
  - `question_statistics`: either copied from manual JSON or computed (by_type/by_marks/total) when absent.

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
├─ latex-dual-layer/
│  ├─ latex_dual_layer_attacked.tex
│  ├─ latex_dual_layer_attacked.pdf
│  ├─ latex_dual_layer_final.pdf
│  ├─ latex_dual_layer_compile.log
│  ├─ latex_dual_layer_log.json
│  └─ metadata.json (cache of render summary + artifact pointers)
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

### `latex-dual-layer/`
- `latex_dual_layer_attacked.tex`: LaTeX source after substring replacements with `\duallayerbox` macros.
- `latex_dual_layer_attacked.pdf`: compiled PDF prior to visual overlay (pure text layer).
- `latex_dual_layer_final.pdf`: dual-layer result (overlay of original page imagery atop manipulated text).
- `latex_dual_layer_compile.log`: concatenated stdout/stderr from the two `pdflatex` passes.
- `latex_dual_layer_log.json`: question-by-question diagnostics (original/replacement text, match offsets, status).
- `metadata.json`: cached summary returned by `LatexAttackService.execute` (counts, durations, artifact paths).
- Final attacked PDF is also copied to `enhanced_latex_dual_layer.pdf` in the run root for downstream consumption.

## Logs & Metrics
- `logs/live.log` (optional) stores raw events if streaming is enabled.
- `metrics.json` can be exported to summarize stage durations and effectiveness.
- `validation.json` records results of renderer validation (pass/fail, error details).

## Developer Notes
- When editing substring mappings, run `SmartSubstitutionService.sync_structured_mappings` to keep `structured.json` accurate.
- Structured data is deep-copied during reruns (see `PipelineConfig` cloning logic). Ensure additions to DB models are mirrored in JSON to keep reruns consistent.

Update this file if new artifacts or JSON structures are added.
