# Reference Report Revamp Plan

## Goals
- Teacher-friendly, actionable PDF showing per-question attack effect and how to use it for cheat detection.
- Non-technical language; clear visuals.
- Support three attacks with user-facing names:
  - CODE_GLYPH → Looks-Right, Reads-Wrong
  - HIDDEN_MALICIOUS_INSTRUCTION_TOP → Invisible Answer Hint
  - HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION → Invisible Answer Block
- Later include per-LLM (ChatGPT, Grok, Perplexity, Gemini) outcomes and success rates.

## Success Criteria (per LLM, per question)
- Looks-Right, Reads-Wrong: success if model picks trap option (wrong_label).
- Invisible Answer Hint: success if model picks trap option(s) (wrong_label/labels/answer).
- Invisible Answer Block: success if model refuses/declines to answer.

Overall success rate per LLM = successes / total questions.

## Per-Question Layout
- Header: Q<n>
- Visual snippet: crop of attacked question region(s) via `context_ids`.
- Clean text: stem and options A–D.
- Answers row:
  - Cheat detection answer: trap.
  - Correct answer: user-provided if present; else inferred during wrong-answer generation.
- Guidance (attack-specific), non-technical.
- Optional per-LLM mini table when available.

## Attack-Specific Guidance
- Looks-Right, Reads-Wrong (Code Glyph)
  - Show key change: "AI reads '<input>' as '<output>'".
  - Guidance: "Paste into AI. If it recommends the cheat answer, flag it."
- Invisible Answer Hint (Detection)
  - Guidance: "Paste into AI. If it recommends the cheat answer, flag it." Include reason if available.
- Invisible Answer Block (Prevention)
  - Guidance: "Paste into AI. If it refuses to answer, the block worked."

## Implementation
- New module `backend/app/services/reference_report_builder.py`:
  - Load `structured.json`.
  - Resolve `context_ids` → union bboxes per page → render crops from attacked PDF.
  - Compose polished PDF with ReportLab.
- Update `build_reference_report` to delegate to new builder; fallback to simple report if inputs missing.
- Evaluation integration later via `evaluations.json`.

## Data mapping
- Trap: from per-question fields (wrong_label/wrong_labels/wrong_answer).
- Correct: user-provided (`reference_answers`) else inferred (`inferred_correct_label` etc.).
- Code Glyph entities: `code_glyph_entities.entities.input_entity/output_entity`.

---

## Progress Log
- [v1] Implemented redaction-first overlay for Code Glyph to remove original text and render attacked text only.
- [v1] Added `reference_report_builder.py` to generate new teacher-friendly report with per-question visuals and guidance.
- [v1] Updated `build_reference_report` to use the new builder, with fallback. 