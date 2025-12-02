# Operations, Workflow & Troubleshooting

This playbook captures daily development routines, testing expectations, and troubleshooting tips for the AntiCheatAI simulator.

## Daily Workflow

1. **Sync & Install**
   - `git pull` (ensure you are on `AntiCheat-v0.0`).
   - Activate backend venv (`source backend/.venv/bin/activate`), run `pip install -r requirements.txt` if dependencies changed.
   - `npm install` inside `frontend/` when package.json updates.
2. **Start Services**
   - Backend: `python backend/run.py` (auto-applies migrations).
   - Frontend: `npm run dev` (http://localhost:5173).
3. **Run a Pipeline**
   - Upload a PDF from the dashboard.
   - Monitor stage chips and the run bar chips (document, downloads, classrooms); keep the developer console open for logs.
4. **Manipulate & Validate**
   - Use Smart Substitution tools; validate suspicious questions via the stage panel.
   - Resume Download PDFs after edits; ensure attacked PDFs land in `artifacts/` and the downloads chip increments.
5. **Classroom Simulation**
   - Use the Classroom action button once downloads exist; generate at least one dataset per run and examine summary stats.
   - Evaluate the dataset via the Evaluation action and review cheating distributions.
6. **Overlay Spot-Check**
   - Inspect `assets/<method>_overlays/` for selective crop PNGs and compare against overlay summaries in the developer console.
7. **Log Findings**
   - Capture key observations/screenshot for PRs.
   - Update documentation if behaviour differs from expectations.

## Testing Strategy

- **Backend** – `pytest` (targeted modules under `backend/tests/` or individual scripts like `test_fresh_run_api.py`). Some legacy tests are pending clean-up—document new ones as they are added.
- **Schema/Migration Checks** – Run `flask db upgrade --sql` to preview generated SQL or `flask db upgrade` against a disposable Docker DB before shipping schema changes.
- **Frontend** – No formal test suite; run `npm run lint` and smoke-test the UI.
- **Manual Regression** – Use demo PDFs to ensure pipeline and classroom stages still execute end-to-end after changes.

## Logging & Monitoring

- **Live Logs** – Toggle the developer panel via the header switch. Channels include stage names (`smart_reading`, `pdf_creation`), `pipeline`, and `ai_clients`.
- **Server Logs** – `tail -f backend/backend_server.log` for Flask output and stack traces.
- **Structured Logs** – Query `pipeline_logs` table or inspect `data/pipeline_runs/<run>/artifacts/logs/` when available.
- **Overlay Diagnostics** – Review `manipulation_results.debug.<method>.overlay` in `structured.json` and the crop assets under `assets/<method>_overlays/` when investigating geometry issues.
- **Metrics** – Check `performance_metrics` for stage durations and custom instrumentation.

## Troubleshooting

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Pipeline stuck on `smart_substitution` | Stage paused awaiting manual action | Click "Resume PDF Creation" (Stage 4) once mappings confirmed. |
| `Failed to generate classroom dataset` | No attacked PDF available or invalid payload | Verify Stage 4 completed, ensure `attacked_pdf_method` matches an existing `enhanced_pdfs` entry. |
| `relation "answer_sheet_runs" does not exist` | Migrations not applied | Restart backend (auto-migration runs) or `flask db upgrade`. |
| PDFs not rendering in UI | Backend returned absolute path or missing artifact | Inspect `enhanced_pdfs` paths, ensure files exist relative to run directory. |
| 500 errors during evaluation | Dataset has zero students or corrupted records | Regenerate the dataset; check logs for detailed exception. |
| Overlay crops missing | Geometry not available or document enhancement skipped | Confirm Smart Substitution produced bounding boxes, rerun Download PDFs, inspect logs for “full-page overlay applied”. |
| OpenAI/Mistral errors | Missing/expired API key | Confirm environment variables in `.env`, retry with valid keys. |

## Release Hygiene

- **Branches** – Cut feature branches from `AntiCheat-v0.0`. Rebase as needed; avoid committing directly to the release branch.
- **Commits** – Keep changes atomic; include doc updates alongside code.
- **Pull Requests** – Provide reproduction steps, highlight new documentation, attach screenshots of UI changes and classroom analytics when applicable.
- **Changelog** – Record notable releases, migrations, or schema changes in team communications (no formal changelog file currently).

## Operational Commands

```bash
# Inspect pipeline stages for a run
psql fairtestai -c "SELECT stage_name, status, duration_ms FROM pipeline_stages WHERE pipeline_run_id = '<run>' ORDER BY started_at;"

# Drop and recreate local Postgres database (danger!)
dropdb fairtestai && createdb fairtestai

# Remove artifacts for a specific run (after backing up if needed)
rm -rf backend/data/pipeline_runs/<run-id>

# View classroom evaluation summary
jq '.' backend/data/pipeline_runs/<run-id>/classroom_evaluations/<classroom_key>/evaluation.json
```

> **Platform tips:** On Windows, run these commands from WSL or adjust paths (e.g., `\\wsl$\...`). macOS/Linux users can execute them directly in Terminal/iTerm.

## Keeping Operations Docs Current

- Update this file when workflow steps change (e.g., new lint command, additional environment requirement).
- Capture common errors with clear outcomes; a good troubleshooting table saves future engineers hours.
