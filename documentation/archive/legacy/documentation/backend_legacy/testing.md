# Testing & Validation (Backend)

While automated coverage is limited today, the repo provides scaffolding and manual checklists to ensure pipeline stability.

## Test Suite

- `pytest` target: `backend/test_renderer_regression.py` (disabled in CI but can be run locally once dependencies are installed).
- Additional tests can live under `backend/tests/` (create as needed). Configure `PYTHONPATH=backend` before running.

### Running Tests Locally

```bash
cd backend
source .venv/bin/activate  # ensure virtualenv is active
pytest -q
```

If `pytest` is missing, install from `requirements-dev.txt` (create this file if we expand the suite).

## Manual Verification Checklist

1. **Smart Reading**
   - Upload a baseline PDF to `/api/pipeline/start`.
   - Verify `structured.json` and AI outputs exist under `backend/data/pipeline_runs/<run>/`.
2. **Content Discovery**
   - Inspect `pipeline_logs` for fusion messages (OpenAI Vision vs Mistral).
   - Confirm `question_manipulations` rows are populated.
3. **Mapping Edits**
   - Use the React UI to adjust substring mappings.
   - Trigger `PUT /api/questions/<run>/<question_id>/manipulation`; verify DB + JSON sync.
4. **PDF Creation**
   - Resume pipeline; check `after_stream_rewrite.pdf` and `final.pdf` artifacts in both `stream_rewrite-overlay/` and `redaction-rewrite-overlay/`.
   - Ensure validation logs report success.
5. **Results Generation**
   - Confirm run reaches `status=completed` and UI summary loads without errors.

## Validation Utilities

- `validate_output_with_context` (in `base_renderer.py`) enforces that original text is absent and replacements appear exactly once.
- `ImageOverlayRenderer` captures snapshot counts; overlay effectiveness is reported via `live_logging_service`.
- `PerformanceMetric` entries record stage durations (useful for regressions).

## Future Enhancements

- Add unit tests for span reconstruction (Method 2) using synthetic PDFs.
- Mock AI providers for deterministic `smart_reading`/`effectiveness_testing` tests.
- Introduce golden-run regression tests (compare produced artifacts with fixtures).

Keep this document updated as the test suite evolves or when new validation tools are introduced.
