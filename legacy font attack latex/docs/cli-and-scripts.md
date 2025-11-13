# CLI & Script Reference

The repository bundles numerous Python scripts for experimenting with font manipulation. This guide summarizes each script, its purpose, and how to run it safely.

> Many scripts overlap in functionality; prefer the backend API or the consolidated demos unless you need a specific behaviour highlighted below.

## Root-Level Python Scripts

| Script | Description | Usage Notes |
| --- | --- | --- |
| `binary_font_manipulator.py` | Low-level helpers for editing TrueType binary tables to match the paper’s methodology. | Used as a library by higher-level scripts; rarely executed directly. |
| `create_deceptive_pdf.py` | Generates a PDF showcasing deceptive font behaviour using predefined mappings. | Requires XeLaTeX; configure `xelatex` on your PATH. |
| `create_demo_pdf.py` | Legacy demo generator for early prototypes. | Superseded by `working_solution.py`, but kept for reference. |
| `customizable_manipulation.py` | Parameterised CLI for crafting arbitrary visual/hidden word pairs. | Accepts command-line arguments; inspect `--help`. |
| `enhanced_font_manipulator.py` | Implements precise `idDelta` modifications with analysis utilities. | Serves as a library; see `test_font_manipulation.py` for examples. |
| `font_manipulation_api.py` | Historical standalone API script predating the current Flask backend. | Not maintained—use `backend/app.py` instead. |
| `font_manipulation_demo.py` | GUI-less walkthrough of the manipulation workflow. | Great for automated demos when GUI access is limited. |
| `font_manipulation_gui.js` / `FontManipulationGUI.css` | Vanilla JS demo shipped with the research bundle. | Embedded in `index.html`. |
| `font_manipulator.py` | Early orchestrator coordinating glyph remaps. | Acts as a helper for legacy scripts. |
| `generate_pdf_example.py` | Simple proof-of-concept for generating PDF outputs. | Useful for smoke-testing XeLaTeX availability. |
| `interactive_demo.py` | Interactive CLI demo prompting for words and generating PDFs on demand. | Depends on `Roboto.ttf` and XeLaTeX. |
| `perfect_manipulation.py` | Reproduces the “perfect” manipulation described in the paper. | Outputs `perfect_manipulation.pdf`. |
| `proper_paper_implementation.py` | Implements the paper using OpenType ligatures; alternative approach to truly selective. | Exports `paper_implementation_font.ttf` and `paper_impl_hello_hides_world.pdf`. |
| `run_complete_demo.py` | End-to-end orchestrator that exercises multiple modes and assembles outputs. | Good for regression testing all flows at once. |
| `selective_manipulation.py` / `true_copy_manipulation.py` / `working_solution.py` | Iterative improvements leading to the final truly selective solution. | Retained for comparison; examine to understand algorithm evolution. |
| `truly_selective_manipulation.py` | CLI mirroring the backend’s truly selective mode with detailed logging. | Generates `normal_font.ttf`, `deceptive_font.ttf`, PDF, and `logs/truly_selective_<timestamp>/steps.log`. |
| `verify_pua.py` | Validation utility for Private Use Area mappings. | Use after running PUA-based manipulations. |

## Reference Fonts & Outputs

While not scripts, many `.ttf`, `.pdf`, and `.txt` files accompany the scripts above. Refer to [`fonts-and-artifacts.md`](fonts-and-artifacts.md) for descriptions and provenance.

## General Execution Tips

1. **Python Environment**: Use Python 3.10+ with `pip install -r requirements.txt` (and `backend/requirements.txt` for the API).
2. **XeLaTeX Dependency**: PDF generators rely on XeLaTeX. Install MacTeX or TeX Live and ensure `xelatex` is reachable.
3. **Fonts**: Most scripts default to `Roboto.ttf`; place alternative base fonts in the working directory or pass explicit paths.
4. **Logging**: New logging directories are created automatically for the truly selective flow. Check `backend/outputs/logs/` or `logs/` in the project root for CLI runs.
5. **Cleanup**: Generated PDFs and TTFs accumulate quickly. Prune `backend/outputs/` and root-level outputs after experiments to keep the repo tidy.

## Update Checklist

- Add a new table row whenever a script is created or retired.
- Note significant behavioural changes (new command-line flags, logging formats, dependencies).
- Keep cross-references (`fonts-and-artifacts.md`, backend/frontend docs) aligned when moving or renaming assets.
