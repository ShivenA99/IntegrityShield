# FairTestAI Advanced Pipeline Build Plan

## Repository Context
- **Target repository**: `/Users/shivenagarwal/Downloads/fairtestai_-llm-assessment-vulnerability-simulator-main`
- **Source assets**: `/Users/shivenagarwal/code_code_glyph/`

## Current System Snapshot
- Legacy implementation preserved under `legacy/` for reference.
- Fresh Flask backend (`backend/`) with modular services, SQLAlchemy models, and async-capable pipeline orchestrator.
- New React + Vite frontend (`frontend/`) with eight-stage pipeline UI, developer console, and context-driven state management.
- Dual-layer PDF enhancement integrated (PyPDF2-based invisible/visible text layering). Additional renderers scaffolded for image overlay, font manipulation, and content-stream rewriting.

## Pipeline Architecture
1. **Smart Reading** – PyMuPDF extraction populates `structured.json`, captures assets and fonts.
2. **Content Discovery** – Regex heuristics convert extracted text to question objects persisted in `question_manipulations`.
3. **Answer Detection** – Heuristic/AI-enabled gold answer selection with confidence tracking.
4. **Smart Substitution** – Universal character mapper (Unicode + ASCII strategies) & substring manipulator generate replacements; effectiveness scored and persisted.
5. **Effectiveness Testing** – Multi-model tester simulates (or executes, when API keys provided) LLM evaluation, storing per-model outcomes.
6. **Document Enhancement** – Prepares enhancement method records for dual-layer, image overlay, font manipulation, and content stream workflows.
7. **PDF Creation** – Renderer registry generates enhanced PDFs (dual-layer currently active), updates metadata and structured results.
8. **Results Generation** – Aggregates run metrics, updates processing stats, finalizes pipeline run.

## Data Model Highlights
- `pipeline_runs` tracks global status, structured data snapshot, and config.
- `pipeline_stages` records progress, duration, and payloads per stage.
- `question_manipulations` stores per-question mappings and AI effectiveness.
- `character_mappings`, `enhanced_pdfs`, `ai_model_results`, and `performance_metrics` provide audit trails and analytics.

## Configuration & Required Secrets
Set the following environment variables (e.g., in `backend/.env`):
- `FAIRTESTAI_DATABASE_URL` – PostgreSQL connection string.
- `FAIRTESTAI_SECRET_KEY` – Flask secret key.
- `FAIRTESTAI_PIPELINE_ROOT` – Filesystem root for pipeline artifacts (defaults to `data/pipeline_runs`).
- `FAIRTESTAI_DEFAULT_MODELS` – Comma-separated LLM identifiers (default: `gpt-4o-mini,claude-3-5-sonnet,gemini-1.5-pro`).
- `OPENAI_API_KEY` – Required for actual LLM testing.
- `ANTHROPIC_API_KEY` – Optional second provider.
- `GOOGLE_AI_KEY` – Optional third provider.
- `FAIRTESTAI_CORS_ORIGINS` – Frontend origin whitelist (e.g., `http://localhost:5173`).

_The orchestrator gracefully simulates model calls when API keys are absent, but real evaluations and cost tracking require valid keys._

## Setup & Migration Notes
1. Create and activate Python venv; install `backend/requirements.txt`.
2. Initialize database: `flask db init` (first run), `flask db migrate`, `flask db upgrade`.
3. Install frontend dependencies: `npm install` in `frontend/`.
4. Run backend (`python run.py` or `flask run`) and frontend (`npm run dev`).

## Testing Strategy
- **Unit Tests** (to be authored):
  - `tests/test_pipeline_orchestrator.py` for stage transitions & skip logic.
  - `tests/test_smart_substitution.py` covering mapping strategies and substring generation.
  - `tests/test_dual_layer_renderer.py` verifying layered text output and mapping counts.
- **Integration Tests**: End-to-end pipeline execution on fixture PDF to validate database writes, structured data, rendered PDFs.
- **Frontend Tests**: React Testing Library specs for `PipelineContainer`, context providers, and developer tools toggles.

## Outstanding Enhancements
- Implement real font remapping (Approach 1) leveraging `fontTools` and assets in `code_code_glyph/advanced_approaches.py`.
- Upgrade image overlay and content stream renderers with precision positioning utilities from the source assets.
- Wire `LLMPDFTester` for actual OpenAI vision/API evaluations when credentials are available.
- Expand developer tooling (live DB inspector queries, structured diff viewer).
- Harden polling, add websocket push notifications for stage completion.

## Next Steps Checklist
1. Provide production-ready environment variables & API keys (OPENAI/ANTHROPIC/GOOGLE) for full AI evaluation.
2. Configure PostgreSQL database and run initial migrations.
3. Develop automated tests as outlined above.
4. Iterate on enhancement renderers using remaining source assets for full fidelity manipulation.
