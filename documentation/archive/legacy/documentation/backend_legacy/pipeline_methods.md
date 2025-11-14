# PDF Generation Methods

During the `pdf_creation` stage we currently produce two primary PDF variants. Both are written to `backend/data/pipeline_runs/<run-id>/artifacts/` but are not yet surfaced directly in the UI.

## Method A — Stream Rewrite (“content_stream_overlay”)

1. **Renderer:** `ContentStreamRenderer` (`backend/app/services/pipeline/enhancement_methods/content_stream_renderer.py`).
2. ** approach:**
   - Reads the original PDF, parses content streams (`Tj`/`TJ`) for spans that match substring mappings.
   - Rewrites text objects to inject manipulated strings.
   - Captures overlay snapshots from the original PDF (`overlays.json`, `snapshots/*.png`) to preserve visual fidelity.
   - After rewriting, applies image/text overlays to ensure appearance matches the original document even if fonts/spacing differ.
3. **Artifacts:**
   - `stream_rewrite-overlay/after_stream_rewrite.pdf` — PDF after text rewrites, before overlay.
   - `stream_rewrite-overlay/final.pdf` — Final dual-layer PDF (stream rewrite + overlay).
   - `stream_rewrite-overlay/overlays.json`, `snapshots/` — overlay metadata and PNG snapshots.
4. **Validation:**
   - `validate_output_with_context` ensures original substring no longer appears and replacement appears once.
   - Alignment issues here affect overlay coverage (current area of active debugging).

## Method B — PyMuPDF Overlay (“pymupdf_overlay” / redaction-based)

1. **Renderer:** `PyMuPDFRenderer` & `ImageOverlayRenderer`.
2. **Approach:**
   - Rather than editing text streams, uses PyMuPDF to redact the original substring bounding boxes and draw image/text overlays on top.
   - Ensures perfect visual fidelity by superimposing captured images/transparent text.
   - Less susceptible to span drift but lacks precise text-layer manipulation (selection returns overlay text).
3. **Artifacts:**
   - `redaction-rewrite-overlay/after_rewrite.pdf` and `redaction-rewrite-overlay/final.pdf`.
   - Overlay assets mirror Method A (snapshots etc.).

## Processing Order

`PdfCreationService` runs stream rewrite first, followed by PyMuPDF overlay. The idea is to get a content-layer replacement (for text extraction and copying) and a visual overlay (for perfect appearance) so the final PDF can deliver both benefits.

## Current Challenges

- Method A needs more precise reconstruction of spans so overlays hide only the manipulated string without covering adjacent text.
- Both methods store metadata in `EnhancedPDF` records for later inspection (size, effectiveness, overlay coverage).

Update this document whenever we introduce new rendering strategies or expose these PDFs in the UI.
