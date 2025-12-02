# Environment Setup

This guide covers local development prerequisites for both backend and frontend layers.

## Prerequisites

- **Python 3.9+** (use `pyenv` or system Python). The repo currently targets 3.9 due to PyMuPDF compatibility.
- **Node.js 18+** (for Vite + React tooling).
- **Poetry/Pip**: either works; repo currently uses a plain `requirements.txt` + `venv` approach.
- **SQLite** (included with Python) for local DB. Production can switch to Postgres.
- **System Libraries**:
  - PyMuPDF (fitz) requires libmupdf – install via `brew install mupdf-tools` (macOS) or appropriate package on Linux.
  - `poppler` optional if you need additional PDF utilities.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in API keys for Mistral/OpenAI
flask db upgrade            # if/when migrations exist
flask run                   # or `python app.py`
```

Key environment variables:
- `FLASK_APP=app`
- `FLASK_ENV=development`
- `OPENAI_API_KEY`, `MISTRAL_API_KEY`
- `PIPELINE_DEFAULT_MODELS`, `PIPELINE_DEFAULT_METHODS` (optional overrides)

## Frontend Setup

```bash
cd frontend
npm install
npm run dev         # launches Vite dev server on http://localhost:5173
```

Configure the proxy in `vite.config.ts` if the backend is running on a non-default port.

## Developer Conveniences

- **Auto Reload:** Flask debug mode plus Vite HMR give instant feedback on code changes.
- **Logging:** Tail logs via `tail -f backend_server.log` or open the Developer Console in the UI.
- **Database Browser:** SQLite DB located at `backend/data/integrityshield.db` (inspect with `sqlite3` or DB Browser).

Keep this document updated when dependencies or setup steps change.
