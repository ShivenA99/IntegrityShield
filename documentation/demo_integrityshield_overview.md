# IntegrityShield Demo Overview

## Current UI Flow

### Pipeline Dashboard (`/`)
- **Run summary bar** – Displays active run id/status, document filename, stage chips, download and classroom counters, plus refresh/reset actions.
- **Stage tracker** – Card per pipeline stage with status, duration, error state, and quick actions (resume, view diagnostics, open artifacts).
- **Stage actions row** – Buttons for Download PDFs, Classrooms, Evaluations, Detection, Vulnerability, and Evaluation reports. Each button reflects availability based on pipeline completion.

### Smart Reading & Content Panels
- **Smart Reading panel** – Left column lists extracted questions with validation badges; right pane shows stem text, options, hidden instructions, and LLM analysis. Users can inspect mapping diagnostics, preview substitutions, and finalize validated mappings.
- **Results panels** – Detection/Vulnerability/Evaluation sections summarize risk metrics and provide download links to JSON/PDF artifacts backed by the pipeline run data.

### Classrooms Page (`/classrooms`)
- **Runs selector** – Quickly switch between available pipeline runs (searchable list sorted by recency).
- **Datasets tab** – Includes a “Create classroom” form (label, notes, attacked PDF variant, advanced cheating config). Below, a searchable/sortable table lists all classroom datasets with status, student counts, summary chips, and actions (Evaluate, Open, Delete).
- **Evaluations tab** – Shows each classroom’s evaluation state, last evaluated timestamp, preview of cheating rate/strategy mix, and buttons to open the detailed report or re-run analytics.

### Classroom Evaluation Detail (`/classrooms/:runId/:classroomId`)
- **Header** – Title, attacked PDF method, student count, navigation breadcrumbs.
- **Summary tiles** – Total students, cheating rate, average & median scores, evaluation status timestamps.
- **Breakdowns** – Strategy distribution chart, score bucket histogram, and cheating source counts.
- **Student table** – Per-student metrics (cheating flag, strategy, score, copy fraction, paraphrase style, average confidence) with sorting/filtering.
- **Actions** – Buttons to return to the classroom list or re-run the evaluation.

## `structured.json` Schema (Run `3e40c4f8-b0d4-4b17-930c-e3bb8a37105f`)

### Top-Level Keys

| Key | Description |
| --- | --- |
| `ai_extraction` | Raw outputs and metadata from AI-based question extraction (page spans, bounding boxes, OCR confidence). |
| `ai_questions` | Alternative AI-generated question summaries used during quality control. |
| `answer_key` | Parsed answer key payload (source PDF path, `status`, `responses` dict keyed by question number, confidence/rationale, and `coverage` stats). |
| `assets` | References to supporting files (images, tables) extracted alongside the PDF. |
| `content_elements` | Ordered list of textual and structural elements reconstructed from the doc (used for fallback question detection and overlays). |
| `document` | Core document metadata (source paths, page count, reconstructed PDF/LaTeX/assets directories). |
| `global_mappings` | Cross-question manipulations or glossary substitutions applied uniformly across the document. |
| `manipulation_results` | Per-method details for each enhancement (`enhanced_pdfs.<method>` with paths, render stats, overlays, effectiveness, diagnostics). |
| `performance_metrics` | Timing and cost metrics for each stage/model invocation. |
| `pipeline_metadata` | Run-level metadata (run id, current stage, completed stages, timestamps, configs, answer-key availability, AI sources, data-extraction outputs, gold-generation progress). |
| `question_index` | Fast lookup map from question numbers to internal ids/sequence indices. |
| `questions` | Array of normalized question objects (see below). |
| `reports` | Detection/vulnerability/evaluation report metadata (paths to generated artifacts, status, scores). |

### `questions[]` Objects
Each entry contains:
- Identification: `question_number`, `q_number`, `sequence_index`, `source_identifier`.
- Classification: `question_type`, `subject_area`, `topic`, `subtopic`, `complexity`, `cognitive_level`, `points`, `has_images/formulas/code/tables`.
- Content: `stem_text`, `options` (labels & text or bounding boxes), `original_text`, `stem_bbox`, `option_bboxes`.
- Answers: `gold_answer`, `gold_source`, `gold_confidence`, `answer_metadata` (generator, label, text, rationale, confidence, source).
- Manipulation info: `manipulation.method`, `manipulation.substring_mappings[]` (original/replacement/context/positions/validation meta), `effectiveness_score`, `character_strategy`.
- Extraction provenance: `sources_detected`, `positioning` (page/bbox/spans), `manipulation_id`, `answer_metadata.generator`, `ai_answers` if LLMs were queried.

### `manipulation_results.enhanced_pdfs`
Structure per enhancement method:
- `path`, `relative_path`, `file_path`, `file_size_bytes`.
- `render_stats`: replacements applied, overlay summaries, compile logs, diagnostics, per-page overlays, min font sizes, effectiveness scores.
- `artifact_rel_paths`: attacked tex/pdf/logs stored under `artifacts/<method>/`.
- `created_at` timestamps for each method.

### `answer_key`
- `source_pdf`: path to uploaded answer key.
- `status`: parsing outcome (`parsed`/`pending`/`error`).
- `responses`: map from question number to `{question_number, answer_label, answer_text, confidence, rationale}`.
- `coverage`: counts of parsed entries, matched questions, timestamps.
- `provider`: LLM/model used if auto-parsed (e.g., `openai:gpt-4o-mini`).

### `pipeline_metadata`
- `run_id`, `current_stage`, `stages_completed[]`, `total_processing_time_ms`, `last_updated`, `version`.
- Flags for key assets (`answer_key_available`, `ai_extraction_enabled`).
- `ai_sources_used[]` and `data_extraction_outputs` (tex/assets/pdf/json paths).
- `gold_generation`: totals for gold-answer population (status, counts, updated timestamp).
- `config`: any runtime overrides captured during run creation.

### Other Supporting Sections
- `ai_extraction` / `ai_questions`: preserve raw outputs from GPT-based extraction, including spans, confidences, and fallback alternatives.
- `content_elements`: sequence of body elements (paragraphs, equations, tables) with bounding boxes and style info, used by overlay renderers.
- `reports`: sub-objects for `detection`, `vulnerability`, `evaluation`, each containing `status`, `generated_at`, summary metrics, and artifact relative paths.
- `performance_metrics`: per-stage runtime stats and LLM token usage.

This schema reflects the duplicated demo dataset under `backend/data/pipeline_runs/demo_integrityshield_base/structured.json`, which the new IntegrityShield UI walkthrough will reference.
