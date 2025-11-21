# AntiCheatAI – LLM Assessment Vulnerability Simulator

This repository hosts the end-to-end simulator we use to probe grading vulnerabilities in LLM-assisted educational workflows. It ingests instructor PDFs, weaponises subtle content manipulations, renders multiple attacked variants, and now models whole-class cheating behaviour through synthetic classroom datasets and evaluation analytics.

## Repository Layout

```
backend/        Flask application, pipeline services, Alembic migrations
frontend/       React + TypeScript SPA for orchestration and analysis
documentation/  Living knowledge base (setup, architecture, APIs, data contracts)
data/           Local storage for pipeline runs and shared artifacts (ignored in git)
scripts/        One-off utilities and operational helpers
```

## Quick Start

### Prerequisites

- Python 3.9 (PyMuPDF compatibility), `pip`, and a virtual environment tool
- Node.js 18+ and npm (Vite dev server)
- PostgreSQL 14+ (recommended for JSONB columns) or SQLite for small local experiments
- System packages: `mupdf-tools` (PyMuPDF), `poppler` (optional helpers)
- API keys for any AI backends you plan to exercise (`OPENAI_API_KEY`, `MISTRAL_API_KEY`, etc.)

### Backend

```bash
cd backend
python3 -m venv venv_host
source venv_host/bin/activate
pip install -r requirements.txt
```

**Configure Environment Variables:**

Create a `.env` file in the `backend/` directory with the following required variables:

```bash
# Environment Configuration
FAIRTESTAI_ENV=development
FAIRTESTAI_PORT=8000
FAIRTESTAI_LOG_LEVEL=INFO

# Database Configuration
FAIRTESTAI_DATABASE_URL=postgresql+psycopg://fairtestai:fairtestai@localhost:5433/fairtestai

# Default Models and Methods
FAIRTESTAI_DEFAULT_MODELS=gpt-4o-mini,claude-3-5-sonnet,gemini-1.5-pro
FAIRTESTAI_DEFAULT_METHODS=content_stream_overlay,pymupdf_overlay

# Development Tools
FAIRTESTAI_ENABLE_DEV_TOOLS=true

# Model Configuration
POST_FUSER_MODEL=gpt-5

# API Keys (REQUIRED)
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_AI_KEY=your_google_ai_key_here
MISTRAL_API_KEY=your_mistral_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
```

**Start the Backend:**

Use the provided startup script which automatically loads environment variables and sets up the correct configuration:

```bash
# From the project root directory
bash backend/scripts/run_dev_server.sh
```

The startup script will:
- Load environment variables from `backend/.env`
- Verify required API keys are present
- Set default database URL (SQLite for local dev) and other configuration
- Activate the virtual environment
- Start the Flask server on port 8000

> **Note:** The script automatically sets `FAIRTESTAI_DATABASE_URL` to use SQLite (`sqlite:////.../data/fairtestai.db`) for local development. To use PostgreSQL, override this in your `.env` file. The application factory (`app.create_app`) runs Alembic migrations automatically when `FAIRTESTAI_AUTO_APPLY_MIGRATIONS` is set to `true` (default is `false` in the script).

### Frontend

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173
```

The Vite dev server proxies `/api/*` to the Flask backend (default `http://localhost:8000`). Adjust the proxy in `vite.config.ts` if you change ports.

## Pipeline Overview

Core stages (managed by `PipelineOrchestrator`) run in sequence on a background worker:

1. **smart_reading** – OCR + vision extraction (`SmartReadingService`)
2. **content_discovery** – Fuse multi-source questions, seed DB (`ContentDiscoveryService`)
3. **smart_substitution** – Apply adversarial mappings and geometry validation (`SmartSubstitutionService`)
4. **effectiveness_testing** – Optional re-query against target LLMs
5. **document_enhancement** – Prep overlay/stream/LaTeX resources
6. **pdf_creation** – Render attacked variants (`PdfCreationService`)
7. **results_generation** – Summaries and pipeline metrics

The SPA exposes two additional post-pipeline phases:

- **Classroom Datasets** – Triggered via the Classroom action once downloads exist; `POST /api/pipeline/<run_id>/classrooms` synthesises student answer sheets per attacked PDF. Artifacts and metadata live under `backend/data/pipeline_runs/<run>/answer_sheets/<classroom_key>/`.
- **Classroom Evaluation** – The Evaluation action (`POST /api/pipeline/<run_id>/classrooms/<id>/evaluate`) aggregates student metrics (cheating breakdowns, score distributions) and persists `classroom_evaluations` records with JSON artifacts.

LaTeX-based methods now capture selective overlay crops per manipulated rectangle (`assets/<method>_overlays/*.png`) so analysts can audit replacements alongside the final PDFs.

## Documentation

The latest guides sit under [`documentation/`](documentation/README.md), including:

- Environmental setup & dependency matrix
- Backend architecture, APIs, logging, and migrations
- Frontend component map and stage UX
- Pipeline stage reference plus classroom dataset lifecycle
- Data contracts, database schema, and storage layout
- Model, prompt, and attack configuration
- Operational workflows and troubleshooting playbooks

Start with the [Documentation Index](documentation/README.md) for a curated table of contents.

## Contributing

1. Branch from `AntiCheat-v0.0`, keep commits scoped, and run lint/tests where practical.
2. Update documentation alongside code—docs are now part of the definition of done.
3. Share reproducible runs or screenshots when raising PRs to capture behavioural changes.

Have questions or found a gap? Extend the docs and ping the team in the PR—knowledge here is our shared foundation for future iterations.
