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
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # supply database URL + AI keys
python run.py         # auto-applies Alembic migrations on startup
```

The application factory (`app.create_app`) runs Alembic migrations automatically when `FAIRTESTAI_AUTO_APPLY_MIGRATIONS` is left at its default `true`. Point `FAIRTESTAI_DATABASE_URL` at Postgres to unlock JSONB-backed tables for classroom datasets (`answer_sheet_runs`, `answer_sheet_students`, `classroom_evaluations`).

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

- **Classroom Datasets** – `POST /api/pipeline/<run_id>/classrooms` synthesises student answer sheets per attacked PDF. Artifacts and metadata live under `backend/data/pipeline_runs/<run>/answer_sheets/<classroom_key>/`.
- **Classroom Evaluation** – `POST /api/pipeline/<run_id>/classrooms/<id>/evaluate` aggregates student metrics (cheating breakdowns, score distributions) and persists `classroom_evaluations` records with JSON artifacts.

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
