# Development Workflow

Use this checklist when implementing features or debugging pipeline behavior.

## Daily Flow

1. **Sync Docs** – glance at `documentation/README.md` for the latest structure.
2. **Start Services**
   - Backend: `cd backend && source .venv/bin/activate && flask run`
   - Frontend: `cd frontend && npm run dev`
3. **Upload/Test Run**
   - Use the Upload card or `curl -F original_pdf=@... /api/pipeline/start`.
   - Monitor live logs via Developer Console.
4. **Edit Mappings**
   - Adjust substring mappings in the UI; save (`PUT /questions/.../manipulation`).
   - Run validations/tests from the dashboard when needed.
5. **Resume Pipeline**
   - Click "Resume PDF Creation" after mapping edits.
   - Inspect generated artifacts in `backend/data/pipeline_runs/<run-id>/`.
6. **Iterate**
   - Use rerun button to clone runs with updated code.
   - Record observations in `documentation/operations/change-log.md` when changes are noteworthy.

## Debugging Tips

- **Content Stream Issues**: Compare `after_stream_rewrite.pdf` vs `final.pdf`. Use PyMuPDF to inspect spans (`page.get_text('rawdict')`).
- **Overlay Alignment**: Check `overlays.json` + snapshots; ensure bounding boxes match the span geometry.
- **AI Errors**: Look for 4xx/5xx logs under `ai_clients` channels (Mistral or OpenAI). API keys might be missing or rate-limited.
- **DB Mismatches**: Run `SELECT * FROM question_manipulations` to verify substring mappings after UI edits.

## Pull Request / Merge Checklist

- [ ] Update relevant docs in `documentation/` (architecture, API, etc.).
- [ ] Attach run artifacts or screenshots demonstrating the fix.
- [ ] Note changes in `operations/change-log.md`.
- [ ] Run `npm run lint` (frontend) and `pytest` (backend) if applicable.
- [ ] Ensure rerun button works end-to-end (no 404 loops).

## Quick Commands

```bash
# Tail logs
cd backend && tail -f backend_server.log

# Inspect structured JSON
jq '.' backend/data/pipeline_runs/<run-id>/structured.json

# Explore DB
sqlite3 backend/data/integrityshield.db "SELECT stage, status, duration_ms FROM pipeline_stages ORDER BY id;"
```

Keep this document updated as processes evolve.
