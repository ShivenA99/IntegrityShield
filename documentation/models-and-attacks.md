# Models, Enhancements & Attack Configuration

This reference captures the configurable levers that determine how we generate adversarial content and evaluate model robustness.

## Default Configuration

Environment variables (see `backend/app/config.py`) define defaults:

- `PIPELINE_DEFAULT_MODELS` – comma-separated list of effectiveness testing models (default: `gpt-4o-mini,claude-3-5-sonnet,gemini-1.5-pro`).
- `PIPELINE_DEFAULT_METHODS` – PDF enhancement/rendering methods to run (default: `latex_dual_layer,pymupdf_overlay`).
- `ANSWER_SHEET_DEFAULTS` – nested JSON containing classroom simulation parameters (student counts, cheating rates, score distributions, paraphrase probabilities, subjective LLM settings).

Overriding these env vars changes the baseline for all runs. Per-run overrides can be supplied in the API payload (`POST /api/pipeline/start`) or via the classroom dataset creation body.

## Enhancement Methods

| Method Key | Renderer | Description | Artifacts |
| --- | --- | --- | --- |
| `pymupdf_overlay` | `ContentStreamRenderer` | Manipulates PDF content streams directly, preserving original layout. | `artifacts/stream_rewrite-overlay/final.pdf`, overlays JSON, snapshots. |
| `content_stream_overlay` | Alias of stream rewrite overlay. | Maintains compatibility with legacy naming. | Same as above. |
| `latex_dual_layer` | `LatexAttackService` | Rebuilds pages with adversarial text beneath rendered imagery (dual-layer). | `artifacts/latex-dual-layer/latex_dual_layer_final.pdf`, metadata logs, compile logs. |

Add new methods by implementing a renderer under `backend/app/services/pipeline/enhancement_methods/` and registering it in `DocumentEnhancementService`.

## AI Providers & Clients

| Client | File | Usage |
| --- | --- | --- |
| OpenAI Vision | `services/ai_clients/openai_vision_client.py` | Smart reading (image-to-JSON extraction), substring geometry lookups. |
| Mistral OCR | `services/ai_clients/mistral_ocr_client.py` | OCR fallback and structured page parsing. |
| GPT-4o Mini | `services/intelligence/multi_model_tester.py` | Effectiveness testing (LLM adversarial evaluation). |
| GPT-4o (Validation) | `services/validation/gpt5_validation_service.py` | Per-question validation of manipulated answers. |

API keys are read from environment (`OPENAI_API_KEY`, `MISTRAL_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_AI_KEY`). Missing keys disable the corresponding features gracefully (warnings logged, UI surfaces helpful toasts).

### Subjective LLM Settings

`ANSWER_SHEET_DEFAULTS["subjective_llm"]` toggles whether answer sheet generation calls a higher-fidelity model for subjective questions. Fields:

- `enabled` (bool)
- `model` (string)
- `temperature`, `max_tokens`, `api_key`, `timeout_seconds`

Adjust these when experimenting with qualitative answer synthesis.

## Classroom Simulation Config

`AnswerSheetGenerationService` merges `ANSWER_SHEET_DEFAULTS` with overrides provided in the request payload. Important keys:

- `total_students` – integer (default 100).
- `cheating_rate` – float 0–1 (default 0.35).
- `cheating_breakdown` – fractions for `llm` and `peer`.
- `copy_profile` – partial/full copy probabilities.
- `paraphrase_probability` – share of cheating students who paraphrase.
- `score_distribution` – separate distributions for fair, cheating_llm, cheating_peer students.
- `write_parquet` – if `true`, emits `answer_sheets.parquet` (requires pandas).
- `random_seed` – ensures reproducibility per dataset.

Provide overrides as:

```json
{
  "config": {
    "total_students": 80,
    "cheating_rate": 0.5,
    "random_seed": "section-b-mock"
  }
}
```

## Prompt Catalogue

See [prompts.md](prompts.md) for a detailed list of prompt templates, payload shapes, and locations in code. Highlights:

- OpenAI Vision extraction prompt (smart reading & geometry lookup).
- GPT-4o validation prompt (assessment-focused JSON schema).
- Mistral OCR extraction instructions.

## Extending Attacks & Models

1. **Add a new AI model** – update config defaults, extend `MultiModelTester`, and adjust frontend selectors if user-facing.
2. **Introduce a new cheating strategy** – modify `AnswerSheetGenerationService._simulate_answers` and extend evaluation summaries to track the new label.
3. **Enhance evaluation** – add metrics (e.g., z-score detection) in `ClassroomEvaluationService` and update UI charts.
4. **Document changes** – update this file and [pipeline.md](pipeline.md) so future engineers know how to trigger the new behaviour.
