# Implementation Log

## 2025-08-08 — Phase 1: Prebuilt pair-font core and spacing fix (foundation)

Changes:
- Added `demo/prebuilt_font_factory.py` to generate single-pair mapping fonts for charset v1 (alpha lower+upper+digits+space). Outputs to `demo/prebuilt_fonts/DejaVuSans/v1/` and copies the base font there.
- Updated `demo/enhanced_pdf_generator.py` with a prebuilt rendering path that:
  - Registers the base font once
  - Picks a prebuilt pair-font per entity character position
  - Advances x using base font metrics for consistent spacing
  - Emits metadata including used pair mappings
- Updated `demo/enhanced_main.py` to support `--font-mode prebuilt` and `--prebuilt-dir` flags, branching the pipeline accordingly.
- Relaxed `demo/input_validator.py` to allow entities with letters, digits, and spaces (v1 charset).

How to build prebuilt fonts (v1):
```
python demo/prebuilt_font_factory.py --charset v1 --source-font demo/DejaVuSans.ttf --out-dir demo/prebuilt_fonts/DejaVuSans/v1
```

How to run pipeline in prebuilt mode:
```
python demo/enhanced_main.py --input-string "What is the capital of Russia?" --input-entity "Russia" --output-entity "Canada" --font-mode prebuilt --prebuilt-dir demo/prebuilt_fonts/DejaVuSans/v1
```

Notes:
- Identity pairs are not generated (base font handles them).
- If a required pair font is missing, the renderer logs an error and falls back to base font for that character (visual may not match). A dynamic on-demand cache will be added later.
- Length mismatch handling (Tier A: space-swap; Tier B: width compensation) is planned next. 

## 2025-08-08 — v2 charset (printable ASCII) support
- Extended `demo/prebuilt_font_factory.py`:
  - New `v2` preset (printable ASCII U+0020..U+007E)
  - `--only-chars` to build a small subset for quick tests
- Updated `demo/input_validator.py` to allow printable ASCII for entities and input strings
- Updated `demo/README.md` with v2 build/run instructions 