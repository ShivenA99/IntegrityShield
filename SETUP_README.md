## Project Overview

This repository contains a full-stack LLM Assessment Vulnerability Simulator:

- **Frontend**: React + TypeScript + Vite (located at the repo root)
- **Backend**: Flask + SQLAlchemy + Alembic (located in `backend/`)
- **Database**: PostgreSQL (recommended via Docker)

The app lets you upload a question paper (PDF), optionally an answer key, injects prompt-injection attacks into the questions, and evaluates model behavior. Processed files, questions, and results are persisted in PostgreSQL.

---

## Prerequisites

- Docker Desktop (for PostgreSQL)
- Node.js 18+ (to run the Vite frontend)
- Python 3.10+ (to run the Flask backend)

Optional but recommended:
- `psql` CLI for database inspection

---

## Quick Start (Local Dev)

### 1) Start PostgreSQL in Docker

```bash
# Run a local Postgres container (first time only)
docker run --name fairtestai-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ftai \
  -p 5432:5432 -d postgres:15

# Verify it's running
docker ps
```

The backend expects a `DATABASE_URL` like:
```
postgresql+psycopg://postgres:postgres@localhost:5432/ftai
```

### 2) Configure environment variables

Create or update these files (placeholders shown):

- `backend/.env`
```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ftai
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
```

- `.env` (root) for frontend build-time injection (used by Vite):
```
GEMINI_API_KEY=...
```

Tip: During testing or offline work, you can disable LLM calls in the backend by setting:
```
ENABLE_LLM=0
```
(as an environment variable when you start the Flask server)

### 3) Backend (Flask API)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run DB migrations
export FLASK_APP=run.py
flask db upgrade

# Start the API (on port 5001 to avoid macOS AirPlay conflicts on 5000)
# Option A (recommended during dev):
python -c "from app import create_app; app = create_app(); app.run(debug=True, host='0.0.0.0', port=5001)"

# Option B (flask CLI):
# export FLASK_RUN_PORT=5001
# flask run --host 0.0.0.0
```

API base: `http://127.0.0.1:5001`

### 4) Frontend (Vite + React)

```bash
# From the repo root
npm install
npm run dev
```

Frontend dev server: `http://localhost:5173`

The Vite proxy is configured in `vite.config.ts` to forward `/api` to the backend (default: `http://127.0.0.1:5001`).

---

## End-to-End Test

- Open the app at `http://localhost:5173`
- Upload a question paper PDF (answer key optional)
- Click to run the attack simulation
- On success you’ll receive an `assessment_id` and see download links

CLI sanity check for the upload route (should return 201):
```bash
curl -s -S -X POST \
  -F "original_pdf=@/absolute/path/to/your.pdf;type=application/pdf" \
  -F "attack_type=Hidden Malicious Instruction (Prepended)" \
  http://127.0.0.1:5001/api/assessments/upload
```

---

## Project Structure (High-level)

```
.
├─ App.tsx                        # Root React component
├─ components/                    # UI components (Header, Footer, PdfUpload, DownloadLinks, ...)
├─ services/
│  ├─ assessmentService.ts       # Frontend API calls to backend
│  └─ geminiService.ts           # Frontend Gemini client (if used)
├─ vite.config.ts                 # Vite config + dev server proxy
├─ index.html / index.tsx         # React entry
├─ types.ts                       # Shared front-end enums and types
│
└─ backend/
   ├─ run.py                      # Flask entry (creates app)
   ├─ requirements.txt            # Backend dependencies
   ├─ migrations/                 # Alembic migrations
   │  └─ versions/               # Migration scripts
   ├─ app/
   │  ├─ __init__.py             # App factory, SQLAlchemy init, CORS
   │  ├─ models.py               # SQLAlchemy models (Assessment, Question, StoredFile, LLMResponse)
   │  ├─ routes/
   │  │  └─ assessments.py       # Upload endpoint, PDF parse, attack inject, report build
   │  └─ services/
   │     ├─ attack_service.py    # AttackType enum + attack application
   │     ├─ pdf_utils.py         # Parse PDFs, inject attacks, build PDFs
   │     ├─ ocr_service.py       # OCR-based question extraction (fallback)
   │     ├─ wrong_answer_service.py # Generates plausible wrong answers
   │     └─ openai_eval_service.py  # Evaluates attacked PDFs using OpenAI
   │
   └─ data/assessments/<uuid>/   # Per-assessment storage of PDFs and artifacts
```

Key runtime directories:
- `backend/data/assessments/<uuid>/` – uploaded original/answers PDFs, attacked and report PDFs
- `backend/output/` – additional debug artifacts

---

## API Overview

- `POST /api/assessments/upload`
  - Form-data fields:
    - `original_pdf` (required, file: application/pdf)
    - `answers_pdf` (optional, file: application/pdf)
    - `attack_type` (string) – e.g. `Hidden Malicious Instruction (Prepended)`
  - Returns: `{ "assessment_id": "<uuid>" }`

- `POST /api/assessments/{id}/evaluate`
  - Triggers LLM evaluation (requires valid OpenAI key if LLM enabled)

- `GET /api/assessments/{id}/download/{file_type}`
  - Download generated artifacts (attacked PDF, report, etc.)

---

## Environment Notes

- Backend reads env via `python-dotenv`; add variables to `backend/.env`.
- Frontend Vite injects `GEMINI_API_KEY` at build-time (`vite.config.ts`), defined in `.env` at repo root.
- To disable LLM during tests: `export ENABLE_LLM=0` before running the backend.

---

## Troubleshooting

- **Port 5000 in use on macOS**
  - AirPlay Receiver often binds to 5000; run backend on 5001:
  ```bash
  export FLASK_APP=run.py
  python -c "from app import create_app; app = create_app(); app.run(debug=True, host='0.0.0.0', port=5001)"
  ```
  - Vite proxy in `vite.config.ts` targets `http://127.0.0.1:5001` by default.

- **Alembic migration errors (revision not found / schema drift)**
  - Ensure migrations are applied:
  ```bash
  cd backend
  source .venv/bin/activate
  export FLASK_APP=run.py
  flask db upgrade
  ```
  - If the DB has an unexpected `alembic_version`, you can reset to the initial migration and upgrade:
  ```sql
  -- In psql connected to your DB:
  UPDATE alembic_version SET version_num = 'f754d45f697f';
  ```
  Then rerun `flask db upgrade`.

- **NOT NULL / missing column errors**
  - Run migrations as above.
  - If `assessments.copy_allowed` is NOT NULL without a default, add one:
  ```sql
  ALTER TABLE assessments ALTER COLUMN copy_allowed SET DEFAULT true;
  UPDATE assessments SET copy_allowed = true WHERE copy_allowed IS NULL;
  ```

- **OpenAI 401 Unauthorized**
  - Set a valid `OPENAI_API_KEY` in `backend/.env` or shell env, then restart the backend.
  - Or disable LLM during testing: `export ENABLE_LLM=0`.

- **Verify services**
  ```bash
  # Backend: 405 means route exists and expects POST
  curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5001/api/assessments/upload

  # Frontend: 200 if up
  curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173
  ```

---

## Google Drive Evaluation Setup

For the OpenAI PDF evaluation path that uploads the attacked PDF to Google Drive and calls the Responses API:

1) Dependencies (already in `backend/requirements.txt`)
   - `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2`, `google-api-python-client`
   - Install via the backend venv: `cd backend && source .venv/bin/activate && pip install -r requirements.txt`

2) Credentials
   - Place your Google OAuth client JSON at: `backend/credentials.json`
   - First run will launch a browser for consent and create `backend/token.json` automatically.
   - To reset auth, delete `backend/token.json` and restart the backend.

3) OpenAI key required
   - Set `OPENAI_API_KEY` in `backend/.env` so the OpenAI calls succeed.

4) Run flow
   - Start backend on port 5001 (as above), then upload a PDF (UI or `curl`).
   - Logs should show: "Google Drive API setup successful", a file ID, and a direct link, followed by OpenAI `responses` calls.

Notes
- If you don’t want evaluation during testing, set `ENABLE_LLM=0` in the backend environment.
- If OCR produces noisy parsing and you want simpler heuristics, set `USE_OCR=0`.

---

## Docker Compose (optional)

A `docker-compose.yml` exists but may require adjustments for the frontend build context. Local dev is recommended via the steps above. If you wish to use Compose, ensure the frontend service points at the repo root or adapt paths accordingly.

---

## Summary

- Start Postgres in Docker
- Configure `backend/.env` and root `.env`
- Run backend migrations and start API on port 5001
- Start Vite frontend on port 5173
- Test upload via UI or `curl`

You're ready to develop, test, and evaluate the simulator locally. 