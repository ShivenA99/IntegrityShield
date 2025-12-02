# AntiCheatAI Demo Environment

This guide explains how to run the read-only AntiCheatAI demo alongside the core IntegrityShield stack.

## 1. Prepare Demo Assets

Add the three demo runs to `demo_assets/` following this structure:

```
demo_assets/
  paper_a/
    input.pdf
    attacked.pdf
    vulnerability_report.json
    reference_report.json
  paper_b/
    ...
  paper_c/
    ...
```

See `demo_assets/schema.md` for the table payload contract. The backend serves these files read-only, so make sure filenames match exactly.

## 2. Backend Configuration

The existing Flask app now exposes demo endpoints under `/api/demo`. Optional environment variables:

- `INTEGRITYSHIELD_DEMO_ASSETS_PATH` – override the default `demo_assets` directory location.

Run the backend as usual:

```bash
cd backend
FLASK_APP=app.run flask run --port 8000
```

## 3. Demo Frontend

The demo UI lives in `frontend-demo/` (Vite + React). Install dependencies once and start the dev server on a dedicated port:

```bash
cd frontend-demo
cp .env.example .env   # adjust API base if backend not on localhost:8000
npm install            # already run by scaffolding, repeat if dependencies change
npm run dev            # serves at http://localhost:5175 by default
```

Endpoints consumed:

- `GET /api/demo/runs`
- `GET /api/demo/runs/<runId>/pdf/input`
- `GET /api/demo/runs/<runId>/pdf/attacked`
- `GET /api/demo/runs/<runId>/vulnerability`
- `GET /api/demo/runs/<runId>/reference`

The UI enforces the staged timing for the vulnerability/reference tables and disables run switching while a demo is active. Use the discreet “Reset Demo” button on the downloads tab to unlock the run selector.

## 4. Production Build (Optional)

To bundle the demo UI for static hosting:

```bash
cd frontend-demo
npm run build
# Output in frontend-demo/dist
```

Serve the `dist/` directory with any static file host or hook into the Flask app if needed.
