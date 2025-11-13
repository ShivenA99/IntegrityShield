# Repository Overview

This guide maps every top-level directory and significant file in `real_code_glyph`, explaining how the pieces fit together.

## Top-Level Layout

| Path | Description |
| --- | --- |
| `backend/` | Flask API, manipulation engines, runtime outputs, and service-specific docs. |
| `frontend/` | Vite/React web application that drives interactive demos against the API. |
| `docs/` | Living documentation set (this folder). |
| `tests/` | Python unit tests targeting manipulation logic. |
| `uploads/` | Drop-in folder for user-supplied fonts or assets processed by CLI scripts. |
| `__pycache__/` | Python bytecode cache (safe to ignore). |
| `requirements.txt` | Consolidated Python dependencies used by CLI tooling; backend maintains its own set under `backend/requirements.txt`. |
| `README.md` | Quickstart instructions (coexists with legacy `README_OLD.md` and supplementary guides). |
| `QUICKSTART.md`, `HOW_TO_RUN.txt`, `FINAL_VERIFICATION.md`, `COMPLETE_SOLUTION.md`, `SUCCESS_SUMMARY.md` | Supporting write-ups shipped with the research hand-off; consult them for historical context. |
| `index.html`, `font_manipulation_gui.js`, `FontManipulationGUI.css`, `preview_component.js`, `PreviewComponent.css` | Standalone browser demo artifacts predating the current Vite frontend. |
| `*.py` in root (e.g., `working_solution.py`, `true_copy_manipulation.py`) | Self-contained scripts for reproducing individual techniques discussed in the paper. These are catalogued in [`cli-and-scripts.md`](cli-and-scripts.md). |
| `*.ttf` (e.g., `Roboto.ttf`, `perfect_font.ttf`) | Fonts produced or consumed by experimentation. Full details: [`fonts-and-artifacts.md`](fonts-and-artifacts.md). |
| `*.pdf`, `*.txt` verification files | Reference outputs illustrating each manipulation path. Documented in [`fonts-and-artifacts.md`](fonts-and-artifacts.md).

## Backend Directory

See [`backend.md`](backend.md) for an in-depth breakdown. Highlights:

- `backend/app.py` — Flask entry point exposing `/api/health`, `/api/modes`, `/api/examples`, `/api/manipulate`, `/api/download/<file>`.
- `backend/manipulators/` — Modular manipulation strategies (`truly_selective.py`, `cyrillic.py`, `pua.py`).
- `backend/outputs/` — Generated fonts, PDFs, and per-run logs (organized by timestamp).
- `backend/fonts/Roboto.ttf` — Base font used for cloning operations.
- `backend/README.md` — API usage instructions.

## Frontend Directory

See [`frontend.md`](frontend.md). Key pieces:

- `frontend/src/App.jsx` — Main application shell.
- `frontend/src/components/` — Form, mode selector, result panel, etc.
- `frontend/index.html`, `vite.config.js`, `package.json` — Vite bootstrap files.

## Tests Directory

Documented in [`testing-and-verification.md`](testing-and-verification.md). Currently hosts targeted unit tests (e.g., `tests/test_truly_selective.py`).

## Root-Level Scripts

Every Python script is described in [`cli-and-scripts.md`](cli-and-scripts.md). Use that reference to decide which tool suits a workflow (e.g., generating PDFs, manipulating fonts, or running GUIs).

## Generated & Reference Artifacts

Comprehensive notes on bundled fonts, PDFs, and verification text files live in [`fonts-and-artifacts.md`](fonts-and-artifacts.md).

## Update Checklist

- When adding a new top-level directory or script, append a row to the table above and update the specialized guide that covers its domain.
- Remove deprecated assets from both the repo and this documentation to avoid drift.
