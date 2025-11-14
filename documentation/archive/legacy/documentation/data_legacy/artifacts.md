# Run Artifacts & File Conventions

Each pipeline run creates a directory under `backend/data/pipeline_runs/<run-id>/`. Understanding this layout is critical for debugging and regression analysis.

## Directory Layout

```
backend/data/pipeline_runs/<run-id>/
├─ Quiz6.pdf                     # Copy of original upload (name varies)
├─ structured.json               # Canonical structured payload
├─ artifacts/
│  ├─ stream_rewrite-overlay/
│  │  ├─ after_stream_rewrite.pdf
│  │  ├─ final.pdf
│  │  ├─ overlays.json
│  │  └─ snapshots/*.png
│  ├─ redaction-rewrite-overlay/
│  │  ├─ after_rewrite.pdf
│  │  ├─ final.pdf
│  │  └─ snapshots/*.png
│  └─ logs/ (optional)
├─ ai_openai_vision.json         # Raw AI outputs (if persisted)
├─ ai_mistral_ocr.json           # Mistral OCR results
├─ metrics.json                  # Optional stage metrics export
└─ notes.md                      # Optional manual notes per run
```

## Key Files

- **`after_stream_rewrite.pdf`** — Output of Method 2 before overlays are applied. Use this to verify content stream rewrites.
- **`final.pdf`** (in each method folder) — Fully rendered PDF delivered to users (after overlays, validation).
- **`overlays.json` / `snapshots/`** — Records capturing overlay rectangles and PNG snapshots from the original document (used to reconstruct appearance).
- **`structured.json`** — Fused question data, mapping metadata, and pipeline metadata; keep in sync with DB.

## Naming Conventions

- `stream_rewrite-overlay` vs `redaction-rewrite-overlay` identify the rendering approach.
- Snapshot filenames usually follow `<page>_<mapping-id>.png`.
- Additional artifacts (e.g., `ocr-page-1.png`) may appear when debugging.

## Cleanup

- Deleting a run via `DELETE /api/pipeline/<run>` removes this directory.
- Soft-deleting a run leaves artifacts in place (for auditing); the UI hides the run unless "Include deleted" is toggled.

Keep this document updated if new artifact types or folders are added.
