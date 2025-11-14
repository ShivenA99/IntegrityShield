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

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
touch .env  # or copy from a template if you maintain one locally
```

> **Windows note:** Replace `python3` with `py` if needed, and activate the virtualenv via `.venv\Scripts\activate`.

Populate `.env` (or export env vars) with:

```
FAIRTESTAI_ENV=development
FAIRTESTAI_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/fairtestai
FAIRTESTAI_PIPELINE_ROOT=/absolute/path/to/backend/data/pipeline_runs
OPENAI_API_KEY=sk-...
MISTRAL_API_KEY=...
```

> **Tip:** Leave `FAIRTESTAI_AUTO_APPLY_MIGRATIONS=true` (default) to let the app run Alembic `upgrade()` on startup.

Start the server:

```bash
python run.py  # listens on 0.0.0.0:8000
```

Flask runs in debug mode for the `development` config, spawning background threads for pipeline execution. Logs stream to `backend_server.log`.

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
3. Watch the pipeline advance through stage 4; ensure attacked PDFs appear under `backend/data/pipeline_runs/<run-id>/`.
4. Generate a classroom dataset from Stage 5 in the UI; confirm `answer_sheet_runs` rows exist and JSON artifacts land under `answer_sheets/<classroom_key>/`.
5. Run classroom evaluation and check `classroom_evaluations` for a completed record.
6. If using Docker, tail database logs with `docker logs -f fairtestai-db` to confirm connections succeed.

If any step fails, consult [operations.md](operations.md) for troubleshooting tips and logging commands.
