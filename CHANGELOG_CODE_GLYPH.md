# CODE_GLYPH Integration Changelog

- Step 1: Introduce pluggable attack interface
  - Added `backend/app/services/attacks/base.py` with `AttackHandler` interface.

- Step 2: Add CODE_GLYPH skeleton handler
  - Added `backend/app/services/attacks/code_glyph.py` with placeholders for stem application, wrong answer generation, artifact build, and evaluation.
  - Added `backend/app/services/attacks/__init__.py` registry and `get_attack_handler()`.

- Step 3: Extend attack enum
  - Updated `backend/app/services/attack_service.py` to include `AttackType.CODE_GLYPH = "Code Glyph (PoC)"`.

- Step 4: Route branching for build/eval
  - Updated `backend/app/routes/assessments.py` to branch on `AttackType.CODE_GLYPH` for artifact build and evaluation (fallbacks to existing OpenAI flow if handler not present or raises).

- Step 5: Docs
  - `WORKFLOW_AND_DEPENDENCIES.md` remains the source of truth for high-level workflow; CODE_GLYPH will reuse steps 1–2 and diverge at steps 3–6.

Pending (to implement when PoC is ready)
- Wire `CodeGlyphAttack.build_artifacts()` to the PoC generator (may differ from LaTeX builder).
- Implement `CodeGlyphAttack.evaluate()` logic specific to code glyph detection.
- Add new wrong-answer prompt variants if needed (service remains same signature).

Step 6: Config support for fonts
- Added `backend/app/services/attacks/config.py` to read `CODE_GLYPH_FONT_MODE` and `CODE_GLYPH_PREBUILT_DIR` (defaults to repo `backend/data/prebuilt_fonts/DejaVuSans/v4`).
- Wired config into `CodeGlyphAttack` constructor. 