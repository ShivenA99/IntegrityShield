# Backend Guide

The backend is a Flask service that orchestrates font manipulation workflows. This document explains the folder layout, runtime behaviour, logging, and how to extend the service safely.

## Directory Structure

| Path | Description |
| --- | --- |
| `backend/app.py` | Flask entry point wiring CORS, request validation, and the `/api/manipulate` handler. |
| `backend/manipulators/` | Strategy modules implementing individual manipulation modes. |
| `backend/fonts/` | Baseline fonts bundled with the service (currently `Roboto.ttf`). |
| `backend/outputs/` | Generated assets (PDFs, fonts, logs) keyed by UUID and timestamp. Safe to clean between runs. |
| `backend/uploads/` | Temporary holding area for user-uploaded assets. |
| `backend/requirements.txt` | Python dependencies dedicated to the API. |
| `backend/README.md` | Quick usage instructions for the API server. |

## Manipulation Pipeline

1. **Request Intake (`/api/manipulate`)**
   - Expected payload: `{ "mode": "truly_selective" | "cyrillic" | "pua", "visual_word": str, "hidden_word": str }`.
   - Validates word lengths and supported modes before dispatching to a manipulator instance.

2. **Manipulator Execution**
   - Each manipulator exposes `create_manipulation(visual_word, hidden_word) -> dict`.
   - On success, returns references to generated font/PDF files inside `backend/outputs/`.

3. **Response Contract**
   - Returns `success`, `pdf_file`, and optionally `font_file`, `message`, `mode`, `log_dir`.
   - Failures bubble descriptive `error` messages and HTTP 400/500 codes.

## Truly Selective Manipulator

Path: `backend/manipulators/truly_selective.py`

Key behaviours:

- Instantiates variable fonts to a static face using `fontTools.varLib.instancer`, ensuring safe glyph editing.
- Clones glyph outlines from a pristine copy of the base font via `TTGlyphPen`, preserving hinting instructions.
- Copies horizontal metrics (`hmtx`) for each remapped glyph so visual width matches the intended character.
- Writes detailed logs: each run produces `backend/outputs/logs/<timestamp>_<jobid>/steps.log` capturing axis instancing, glyph remaps, and output file names.
- Returns both the normal and deceptive fonts (`<jobid>_normal.ttf` and `<jobid>_deceptive.ttf`) plus the generated PDF `<jobid>.pdf`.

Logging structure example:

```
backend/outputs/logs/20251002_112518_be1e6b74/steps.log
```

Contents include the job ID, timestamp, base font handling, and per-glyph substitutions.

## Other Manipulators

- `cyrillic.py` — Swaps Latin characters with visually similar Cyrillic code points for homoglyph attacks.
- `pua.py` — Rebinds glyphs using Unicode Private Use Area code points for precise control.

Each module follows the same `create_manipulation` signature, making it straightforward to plug in new strategies.

## Outputs Folder

- `*.pdf` — Generated demonstration documents for each request.
- `*_normal.ttf` — Static copy of the base font used for surrounding text.
- `*_deceptive.ttf` — Manipulated font containing remapped glyphs.
- `logs/` — Timestamped logs discussed above.

Consider adding a cleanup cron or script if the folder grows large; do not commit generated outputs to version control unless they serve as fixtures.

## Running the Server

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py  # binds to http://0.0.0.0:5001
```

Use `flask run --port 5001` only if you port the app to Flask CLI conventions; the provided script already handles host/port configuration.

## Extending the Backend

- **New Manipulator**: Add a module under `backend/manipulators/`, implement the `create_manipulation` method, and register it in `app.py`'s `manipulators` dictionary.
- **New Logging Fields**: Update the `log_entries` list in `truly_selective.py` (and any other manipulator) to capture additional analytics. Keep the format human-readable.
- **Error Handling**: All manipulators should return `{'success': False, 'error': 'message'}` on failure; avoid raising exceptions directly to keep API responses predictable.

## Update Checklist

- Update this document whenever manipulators change behaviour or new routes are added.
- Document additional output subfolders or logging formats as they are introduced.
- Ensure `backend/README.md` mirrors any major instruction changes reflected here.
