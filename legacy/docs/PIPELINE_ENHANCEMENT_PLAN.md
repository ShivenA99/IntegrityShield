## Pipeline Enhancement Plan (OCR + Layout + Exact Renderer)

This document captures the agreed plan to extend OCR to full-document structure (text + non-text) and add an exact-layout renderer, while keeping the current LaTeX path as default until validated. Evaluation revamp will be addressed after these changes.

### Goals
- Extract all information from PDFs (text blocks, headers/footers, images/figures, tables, drawings) with coordinates.
- Build a structured JSON representation for the entire document, including question typing and composition.
- Generate attacked PDFs that exactly replay the original layout, applying attacks without visual drift.
- Keep current LaTeX path intact and gate the new renderer behind a feature flag for A/B validation.

### Feature Flags & Config
- `PDF_RENDERER`: `latex` (default) or `mupdf`
- `STRUCTURE_OCR_DPI`: integer DPI for rasterization/crops (default 300)
- Existing: `ENABLE_LLM`, `USE_OCR`, `CODE_GLYPH_*`

### Storage Layout (per assessment run)
- `backend/data/assessments/<uuid>/`
  - `original.pdf`
  - `answers.pdf` (optional)
  - `structured.json` (new; full document model)
  - `assets/` (new; cropped images/tables/figures/drawings)
  - `attacked.pdf`
  - `report.pdf`
- Mirror debug copies to `backend/output/` as today

### Data Model (Structured JSON)
Top-level schema written to `structured.json`:

```json
{
  "document": {
    "assessment_id": "<uuid>",
    "title": "<string>",
    "pages": [
      {
        "page_index": 0,
        "width": 612.0,
        "height": 792.0,
        "dpi": 300,
        "items": [
          {
            "id": "p0-i3",
            "type": "text_block",
            "bbox": [x0, y0, x1, y1],
            "bbox_norm": [nx0, ny0, nx1, ny1],
            "text": "..."
          },
          {
            "id": "p0-i4",
            "type": "image",
            "bbox": [x0, y0, x1, y1],
            "bbox_norm": [nx0, ny0, nx1, ny1],
            "asset_id": "assets/page-0-img-1.png",
            "orig_mime": "image/png"
          },
          {
            "id": "p0-q1",
            "type": "question",
            "bbox": [x0, y0, x1, y1],
            "q_number": "1a",
            "q_type": "mcq_single",
            "stem_text": "...",
            "options": { "A": "...", "B": "..." },
            "matches": [],
            "blanks": [],
            "context_ids": ["p0-c1", "p0-i4"],
            "assets": ["assets/page-0-img-1.png"]
          }
        ]
      }
    ]
  }
}
```

- `type` values: `header`, `footer`, `logo`, `instruction`, `text_block`, `image`, `table`, `figure`, `comprehension`, `question`.
- `q_type` values: `mcq_single`, `mcq_multi`, `true_false`, `match`, `fill_blank`, `short_answer`, `long_answer`, `comprehension_qa`.

### Modules & Files
- New: `backend/app/services/ocr_document.py`
  - Contains dataclasses/pydantic models and schema validators for the structured document.
  - Utilities for bbox normalization, id generation, and JSON (de)serialization.

- Update: `backend/app/services/ocr_service.py`
  - Add `extract_structured_document_with_ocr(pdf_path: Path) -> Dict` that returns the above JSON.
  - Keep existing `extract_text_from_pdf_with_ocr` and `extract_questions_from_pdf_with_ocr` but project from the structured JSON for back-compat.

- New: `backend/app/services/layout_extractor.py`
  - PyMuPDF-based extraction of text blocks, images, drawings, and heuristic tables.
  - Exposes:
    - `extract_layout_and_assets(pdf_path: Path, out_assets_dir: Path, dpi: int) -> Dict` (partial structured JSON without question typing)

- New: `backend/app/services/pdf_renderer_mupdf.py`
  - Exact layout renderer using PyMuPDF (fitz):
    - `build_attacked_pdf_mupdf(ocr_doc: Dict, output_path: Path, attack_type: AttackType) -> Path`
    - Renders original page as background; overlays modified text (attacks) and re-places assets at exact bboxes.

- Update: `backend/app/services/pdf_utils.py`
  - In `build_attacked_pdf(...)`, route to LaTeX or MuPDF based on `PDF_RENDERER` env.
  - Keep LaTeX flow unchanged; ensure zero-width/invisible hidden instruction overlays (already fixed).

- Update: `backend/app/services/wrong_answer_service.py`
  - Add per-`q_type` prompt templates and formatting rules.

### Function Signatures (proposed)
- `layout_extractor.py`
  - `def extract_layout_and_assets(pdf_path: Path, out_assets_dir: Path, dpi: int = 300) -> Dict: ...`

- `ocr_service.py`
  - `def extract_structured_document_with_ocr(pdf_path: Path) -> Dict: ...`
  - Back-compat:
    - `def extract_text_from_pdf_with_ocr(pdf_path: Path, prompt: str | None = None) -> str: ...`
    - `def extract_questions_from_pdf_with_ocr(pdf_path: Path) -> Dict[str, Any]: ...`  (now projects from structured JSON)

- `pdf_renderer_mupdf.py`
  - `def build_attacked_pdf_mupdf(ocr_doc: Dict, output_path: Path, attack_type: AttackType) -> Path: ...`

- `pdf_utils.py`
  - `def build_attacked_pdf(questions: List[Dict], output_path: Path, title: str = "") -> None: ...` (existing)
  - Internally decides renderer based on `PDF_RENDERER`.

### Extraction Logic (Layout + Assets)
- Text:
  - Use `page.get_text('dict')` to collect blocks → coalesce into `text_block` items (preserve line order and bounding boxes).
- Images:
  - `page.get_images()` + `doc.extract_image(xref)` to save PNGs.
  - Derive image bboxes via `page.get_text('rawdict')` image blocks; emit `image` items with `asset_id` + `bbox`.
- Drawings (figures):
  - `page.get_drawings()`; compute bounding regions of grouped lines/paths; rasterize those regions to PNG; emit `figure` items.
- Tables (image-only for now):
  - Heuristic: detect dense ruled-line clusters from `get_drawings()`; rasterize bounding region to PNG; emit as `table` items.
- Headers/Footers/Logos:
  - Identify repeating bboxes across pages; tag as `header`, `footer`, `logo`.

### OCR Structuring (LLM Pass)
- Inputs to LLM:
  - Per-page ordered list: `{id, page_index, bbox, text_excerpt}` for `text_block` items (excerpt to reduce tokens).
  - Asset list: `{id, asset_id, page_index, bbox, type_guess}` for `image`/`table`/`figure`.
- Tasks:
  - Classify document-level items (title, headings, instructions, headers/footers, logos).
  - Detect and classify questions; populate `q_number`, `q_type`, and per-type fields (options, matches, blanks, etc.).
  - Link questions to relevant `context_ids` (comprehension, images, tables) by nearest bbox/page proximity.
- Output: JSON ONLY in the schema defined above; saved as `structured.json`.
- Back-compat: project `structured.json` into legacy `{title, questions[]}` for existing pipeline paths.

### Renderer (MuPDF) – Exact Replay
- Strategy: exact visual replay with minimal overlays.
- Background:
  - Rasterize each original page at `STRUCTURE_OCR_DPI` and place as full-page image to guarantee fidelity.
- Overlays:
  - Hidden malicious/prevention:
    - Insert invisible text (PDF text rendering mode 3) at the document or per-question positions to exist in text layer without affecting layout.
    - Fallback if needed: tiny white off-page placement with appropriate tagging.
  - Code Glyph:
    - Identify target stem/options from `structured.json` by bbox and text.
    - Overlay attacked text within original bbox using glyph mapping and width-aware wrapping (reuse logic akin to `code_glyph_runtime/pdfgen`).
  - Non-text assets:
    - Re-place cropped images/tables/figures exactly at their `bbox` coordinates (no alteration).

### Question Types – Rendering Rules
- `mcq_single`, `mcq_multi`, `true_false`: render stem and options within original text_block bbox; preserve line breaks when possible.
- `match`: render two aligned columns; if original columns are present as text blocks, follow their bboxes.
- `fill_blank`: underline placeholders within stem; preserve original spacing.
- `short_answer`, `long_answer`: draw ruled lines beneath stem as per available space in bbox.
- `comprehension_qa`: render comprehension block once; ensure linked questions follow without page-break separation from context (when feasible).

### Wrong Answer Generation (placeholders; eval later)
- Extend `wrong_answer_service` with per-`q_type` prompt templates and formatting:
  - `mcq_single/mcq_multi`: labels only (A, B, ...), optional rationale.
  - `true_false`: i)/ii) format.
  - `match`: normalized mapping pairs (e.g., `A-3, B-1, ...`).
  - `fill_blank`: token(s) matching placeholders.
  - `short_answer/long_answer`: length/rubric guidance.
  - `comprehension_qa`: answers constrained to linked `context_ids`.
- Attack variants (suffix): `_hidden_top`, `_hidden_prevention`, `_code_glyph` to tailor behaviors.

### API & Integration Changes
- `POST /api/assessments/upload`:
  - After parsing, write `structured.json` and `assets/` to the assessment directory.
  - Choose renderer by `PDF_RENDERER` env; default remains LaTeX.
  - Return paths/urls as today.

### Testing & Validation
- Unit:
  - Schema validation for `structured.json`.
  - Bbox normalization and id determinism.
- Golden/Visual:
  - Side-by-side LaTeX vs MuPDF PDFs; rasterize pages; compute SSIM; confirm negligible diffs outside attacked spans.
- Functional samples:
  - Each q_type (MCQ, TF, match, fill, short/long, comprehension with images/tables).
- Performance:
  - Token bounds by excerpting text blocks; page-batched LLM calls.

### Phased Rollout
1. Scaffolding: feature flag, schema module, directory writers.
2. Layout + asset extractor; write `structured.json` (no LLM yet).
3. LLM structuring; project to legacy format; persist full JSON.
4. MuPDF exact renderer; attacks via overlays; A/B with LaTeX.
5. Per-`q_type` wrong-answer prompt extensions (evaluation revamp to follow).

### Open Items (to confirm during implementation)
- Table detection thresholds and min-size for cropping.
- Maximum page raster DPI (quality vs size); initial default `300`.
- Whether to include vector-to-raster crops for complex drawings by default.

### Notes
- Evaluation pipeline will be redesigned after renderer + structuring are stable.
- Storage costs will increase due to background rasters and asset crops; acceptable per stakeholder guidance. 