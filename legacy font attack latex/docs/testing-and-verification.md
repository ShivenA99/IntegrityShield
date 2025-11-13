# Testing & Verification Guide

Use this guide to validate code changes, reproduce automated tests, and perform manual verification of generated artifacts.

## Automated Tests

### Python Unit Tests

| Test Module | Coverage |
| --- | --- |
| `tests/test_truly_selective.py` | Validates that hidden glyphs in the truly selective manipulator clone geometry and metrics from their visual counterparts. |
| `test_basic_functionality.py`, `test_font_manipulation.py`, `test_extraction.py` | Legacy smoke tests that exercise various manipulation helpers. Review their docstrings before running—some expect system fonts or mocked environments. |

#### Running Tests

```bash
python3 -m unittest tests.test_truly_selective
# or run the entire suite
python3 -m unittest
```

> Install dependencies from `requirements.txt` and ensure `fontTools` is available. Some tests require access to system fonts (`Arial.ttf`, `DejaVuSans.ttf`) and may skip automatically if not found.

## Manual Verification

For each manipulation mode, accompanying PDFs and text files describe the expected behaviour:

- **Truly Selective**
  - PDF: `truly_selective_hello_hides_world.pdf`
  - Guide: `truly_selective_verification.txt`
- **True Copy**
  - PDF: `true_copy_hello_hides_world.pdf`
  - Guide: `true_copy_verification.txt`
- **Paper Implementation**
  - PDF: `paper_impl_hello_hides_world.pdf`
  - Guide: `paper_verification.txt`

Follow the instructions in each verification file: view the red-highlighted word, copy/paste it, and ensure the pasted output matches the hidden word.

## Logging for Audits

- Review `backend/outputs/logs/<timestamp>_<jobid>/steps.log` to confirm glyph substitutions performed by the API.
- For CLI runs, inspect `logs/truly_selective_<timestamp>/steps.log`.

Include these logs when filing bug reports or documenting experiments—they provide evidence of which glyphs were altered.

## Continuous Improvement

- Add a focused unit test alongside any new manipulator features or bug fixes.
- Consider expanding coverage to other manipulation modes (`cyrillic`, `pua`) to ensure regression safety.
- When introducing integration tests (e.g., end-to-end API + frontend flows), describe them here with setup and teardown steps.

## Update Checklist

- Reflect new tests or verification documents immediately.
- Note skipped/expected failures so team members aren’t surprised during CI runs.
- Keep manual verification instructions aligned with the latest PDFs shipped in the repo.
