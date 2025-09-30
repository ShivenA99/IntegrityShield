# Pipeline & Stage Behaviors

The FairTestAI pipeline transforms an input PDF into manipulated variants that expose LLM grading vulnerabilities. The orchestrator executes stages in the order shown below; each stage persists results to SQL and to `backend/data/pipeline_runs/<run-id>/`.

```
smart_reading → content_discovery → (pause) → smart_substitution
→ effectiveness_testing → document_enhancement → pdf_creation → results_generation
```

## Stage Glossary

| Stage | Service | Purpose | Key Inputs | Key Outputs |
| --- | --- | --- | --- | --- |
| `smart_reading` | `SmartReadingService` | Collect raw extraction signals (PyMuPDF, OCR snapshots, AI vision). | Original PDF | Structured JSON (`structured.json`), AI question drafts, discovery logs. |
| `content_discovery` | `ContentDiscoveryService` | Fuse multi-source question data, align with PDF geometry, seed `QuestionManipulation` rows. | Structured JSON, AI outputs | `question_manipulations` with positions/mappings, `pipeline_metadata`. |
| `smart_substitution` | `SmartSubstitutionService` | Apply mapped substitutions (teacher -> target strings), compute character maps, sync DB↔structured JSON. | Question mappings, user edits | Updated substring mappings, character map strategies. |
| `effectiveness_testing` | `EffectivenessTestingService` | Re-query target AI models to evaluate manipulations (optional stage). | Manipulated questions, AI credentials | `ai_model_results`, scoring metrics. |
| `document_enhancement` | `DocumentEnhancementService` | Prepare enhancement methods, gather resources (fonts, overlays) for PDF rewriting. | Structured data, mappings | Enhancement configs, overlay assets folder. |
| `pdf_creation` | `PdfCreationService` | Execute rendering methods (Method 1 & Method 2), validate outputs, store artifacts. | Enhancement assets, original PDF | `enhanced_pdfs` entries, artifacts under `artifacts/`, validation logs. |
| `results_generation` | `ResultsGenerationService` | Compile reports, final metrics, summary output for UI. | All previous artifacts | Summary JSON, pipeline status `completed`. |

## Pause & Resume Flow

1. `smart_reading` and `content_discovery` run automatically on new uploads.
2. After `content_discovery`, the orchestrator pauses the pipeline (`status=paused_for_mapping`) so users can edit substring mappings in the frontend.
3. The UI resumes via `POST /api/pipeline/<run>/resume/pdf_creation` once mappings are ready. The orchestrator restarts from `smart_substitution`.

## Artifacts by Stage

| Stage | Artifact Directory | Notable Files |
| --- | --- | --- |
| `smart_reading` | `data/pipeline_runs/<run>/structured.json`, `ai_*` | AI vision outputs, text extraction, layout metrics. |
| `content_discovery` | DB tables, `structured.json` updated | `question_manipulations`, developer logs (`content_discovery` channel). |
| `smart_substitution` | DB + JSON sync | `character_mappings`, mapping contexts (with bounding boxes/quads). |
| `document_enhancement` | `artifacts/stream_rewrite-overlay`, `artifacts/redaction-rewrite-overlay` | Snapshot PNGs, mask rectangles, precomputed overlays. |
| `pdf_creation` | `artifacts/stream_rewrite-overlay/after_stream_rewrite.pdf`, `final.pdf`, logs | Validation logs (`ContentStreamRenderer`, `PyMuPDFRenderer`). |
| `results_generation` | DB metrics, JSON summary | `performance_metrics`, stage durations, final run metadata. |

## Developer Hooks

- **Live Logging:** `live_logging_service.emit(run_id, stage, level, message, context)` streams to the frontend developer console.
- **Performance Metrics:** `record_metric` persists stage durations & custom KPIs per stage.
- **Validation:** Renderers raise exceptions if validations fail (e.g., original string detected post-render); pipeline orchestration marks the run `failed`.

## Extensibility

- Add new stages by updating `PipelineStageEnum`, mapping the stage to a new service, and adjusting UI stage order.
- Enhancement methods plug into `PdfCreationService` by implementing a renderer under `enhancement_methods/` and registering it in the service configuration.
- Pause/resume points can be introduced by mimicking the existing `content_discovery` pause logic.

Keep this document in sync when pipeline stages change or new artifacts are introduced.
