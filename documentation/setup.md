# Environment Setup & Dependencies

Use this guide to bootstrap a development environment that mirrors production behaviour. The instructions assume macOS or Linux; adapt package installation commands as needed for Windows (WSL recommended).

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.9.x | PyMuPDF currently pins to 3.9 in our virtualenv. |
| Node.js | ≥ 18.0 | Required for Vite, ESLint, and the React dev server. |
| npm | ≥ 9 | Bundled with Node; `pnpm` or `yarn` also work if configured. |
| PostgreSQL | ≥ 14 (recommended) | JSONB support powers classroom datasets; SQLite works for light testing. |
| mupdf-tools | latest | `brew install mupdf-tools` (macOS) / `apt install mupdf` (Linux). |
| poppler-utils (optional) | latest | Handy for ad-hoc PDF inspection (`brew install poppler`). |

## Backend Setup

### 1. Install Dependencies

```bash
cd backend
python3 -m venv venv_host
source venv_host/bin/activate
pip install -r requirements.txt
```

> **Windows note:** Replace `python3` with `py` if needed, and activate the virtualenv via `venv_host\Scripts\activate`.

### 2. Configure Environment Variables

Create a `.env` file in the `backend/` directory with the following configuration:

```bash
# Environment Configuration
FAIRTESTAI_ENV=development
FAIRTESTAI_PORT=8000
FAIRTESTAI_LOG_LEVEL=INFO

# Database Configuration
# For PostgreSQL (recommended for production):
FAIRTESTAI_DATABASE_URL=postgresql+psycopg://fairtestai:fairtestai@localhost:5433/fairtestai
# For SQLite (default in startup script, good for local dev):
# The startup script will override this to use SQLite unless explicitly set

# Default Models and Methods
FAIRTESTAI_DEFAULT_MODELS=gpt-4o-mini,claude-3-5-sonnet,gemini-1.5-pro
FAIRTESTAI_DEFAULT_METHODS=content_stream_overlay,pymupdf_overlay

# Development Tools
FAIRTESTAI_ENABLE_DEV_TOOLS=true

# Model Configuration
POST_FUSER_MODEL=gpt-5

# API Keys (REQUIRED - the startup script will check for these)
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_AI_KEY=your_google_ai_key_here
MISTRAL_API_KEY=your_mistral_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
```

> **Windows paths:** When running outside WSL, use double backslashes for file paths. If you develop inside WSL (recommended), keep Unix-style paths but grant filesystem permissions to your Windows user so the frontend can download artifacts.

> **Database Note:** The startup script defaults to SQLite for local development (`sqlite:////.../data/fairtestai.db`). To use PostgreSQL, set `FAIRTESTAI_DATABASE_URL` in your `.env` file. The script will respect your override.

> **Migrations:** The startup script sets `FAIRTESTAI_AUTO_APPLY_MIGRATIONS=false` by default. To enable automatic migrations, set this to `true` in your `.env` file.

### 3. Start the Backend Server

**Recommended: Use the Startup Script**

From the project root directory, run:

```bash
bash backend/scripts/run_dev_server.sh
```

The startup script (`backend/scripts/run_dev_server.sh`) will:
- Load environment variables from `backend/.env`
- Verify that required API keys (`OPENAI_API_KEY`, `GOOGLE_AI_KEY`) are present
- Set default configuration values (database URL, model settings, etc.)
- Activate the `venv_host` virtual environment
- Start the Flask server on port 8000 (or the port specified in `FAIRTESTAI_PORT`)

**Alternative: Manual Startup**

If you prefer to start manually:

```bash
cd backend
source venv_host/bin/activate
export $(cat .env | xargs)  # Load .env variables
export FAIRTESTAI_DATABASE_URL="sqlite:////$(pwd)/data/fairtestai.db"  # Override for local dev
python run.py  # listens on 0.0.0.0:8000
```

Flask runs in debug mode for the `development` config, spawning background threads for pipeline execution. Logs stream to `backend_server.log` or `/tmp/backend_flask.log` depending on your configuration.

### Fresh Postgres via Docker (Optional)

If you do not have a local Postgres instance, spin up a disposable container:

```bash
docker run \
  --name fairtestai-db \
  -e POSTGRES_USER=fairtestai \
  -e POSTGRES_PASSWORD=fairtestai \
  -e POSTGRES_DB=fairtestai \
  -p 5432:5432 \
  -d postgres:14
```

Point `FAIRTESTAI_DATABASE_URL` at the container:

```
FAIRTESTAI_DATABASE_URL=postgresql+psycopg://fairtestai:fairtestai@localhost:5432/fairtestai
```

To reset the database during development:

```bash
docker stop fairtestai-db
docker rm fairtestai-db
# rerun the docker command above to start fresh
```

You can substitute any custom `docker compose` stack—just ensure the service exposes port `5432` and that credentials match your `.env`.

#### Docker Compose Template

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:14
    container_name: fairtestai-db
    environment:
      POSTGRES_USER: fairtestai
      POSTGRES_PASSWORD: fairtestai
      POSTGRES_DB: fairtestai
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
volumes:
  postgres-data:
```

Run `docker compose up -d db` (or `docker-compose up -d db`) to launch the database. Tear it down with `docker compose down` and remove the volume for a pristine reset: `docker compose down -v`.

#### Connecting to the Container

- `psql postgresql://fairtestai:fairtestai@localhost:5432/fairtestai`
- `docker exec -it fairtestai-db psql -U fairtestai -d fairtestai`

### Database Utilities

- **Initialize schema manually** (optional): `flask db upgrade` if you prefer explicit migrations.
- **Inspect tables**: `psql fairtestai` then `\dt` (Postgres) or `sqlite3 backend/data/fairtestai.db` for SQLite.
- **Reset local data**: Remove `backend/data/pipeline_runs/<run-id>/` for targeted cleanup; avoid `rm -rf data` without confirming you no longer need artifacts.
- **Verify overlays**: Run `ls backend/data/pipeline_runs/<run-id>/assets/<method>_overlays/` to confirm selective LaTeX crops were generated (PNG clips plus overlay logs).

## Frontend Setup

```bash
cd frontend
npm install
npm run dev         # http://localhost:5173
```

On Windows PowerShell use `npm run dev` as normal; if the backend runs on WSL, ensure firewall rules allow access from the browser. On macOS/Linux the command above works unchanged.

The Vite dev server proxies `/api` requests to `http://localhost:8000` by default (see `vite.config.ts`). If you run the backend on another port, update the proxy or set `VITE_BACKEND_BASE_URL`.

### Useful Scripts

- `npm run lint` – ESLint + TypeScript checks.
- `npm run build` – Production bundle output (served from `dist/`).
- `npm run preview` – Static preview of the built bundle.

## Optional Services & Integrations

- **OpenAI / Anthropic / Google AI** – supply API keys to exercise smart reading, validation, and effectiveness testing. Missing keys degrade gracefully (warnings in logs).
- **S3-compatible bucket** – configure `FILE_STORAGE_BUCKET` if you want artifacts mirrored to object storage (not required for local dev).
- **WebSockets** – the developer console uses `flask-sock`; ensure port 8000 is accessible to the browser.

## Verifying Your Environment

1. Launch backend and frontend as described above.
2. Upload a sample PDF (see `demo_assets/`).
3. Watch the pipeline advance through Stage 4 (**Download PDFs**); ensure attacked PDFs appear under `backend/data/pipeline_runs/<run-id>/`.
4. Click the `Classroom` action button (beneath the stage tracker) and generate a dataset; confirm `answer_sheet_runs` rows exist and JSON artifacts land under `answer_sheets/<classroom_key>/`.
5. Use the `Evaluation` action to run classroom analytics and check `classroom_evaluations` for a completed record.
6. Inspect `assets/<method>_overlays/` to verify selective overlay crops were saved for debugging.
7. If using Docker, tail database logs with `docker logs -f fairtestai-db` to confirm connections succeed.

If any step fails, consult [operations.md](operations.md) for troubleshooting tips and logging commands.
