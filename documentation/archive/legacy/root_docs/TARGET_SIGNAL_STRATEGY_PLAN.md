# Target & Signal Strategy Plan – Smart Substitution Refresh

## Executive Summary

**Goal**: Give GPT-5 clear guardrails for generating adversarial mappings that either (1) drive objective questions toward a specific wrong answer (`target` path) or (2) plant verifiable cues for subjective responses (`signal` path), while keeping PDF creation resilient when mappings are missing.

**Scope**:
- Rework auto-mapping prompts, metadata, and validation flows to differentiate `target` vs `signal` strategies.
- Prepare MCQ-focused few-shot exemplars drawn from run `d9788165-7453-426d-a37d-3f051312623a` (questions 2, 6, 8, 9, 10).
- Extend validator output to report diagnostics without rejecting signal-based mappings.
- Harden pdf_creation so the pipeline finishes even when some questions lack mappings, persisting skip reasons for audit.

---

## 1. Current MCQ Exemplars (Run d9788165…)

| Q# | Stem (abridged) | Gold | Mapping | Intended Target |
|----|-----------------|------|---------|-----------------|
| 2 | "If T(n) = 5n^3 + 4n + 1…" | B | `the correct → nsquared times the` | **D** (explicit flip needed) |
| 6 | "When an array is already sorted…" | B | `implemented with slight → executed in swap-costly` & `already → not` | **A** |
| 8 | "Suppose a particular tree structure…" | B | `crucial → irrelevant` | **A** (already stored) |
| 9 | "If a heap is implemented using an array…" | B | `describe → misdescribe` | **A** |
| 10 | "Which property might always hold in a max heap?" | B | `always → never` | **C** |

Notes:
- These mappings respect the safe-span constraint and succeed end-to-end; perfect for GPT-5 few-shot demos.
- Q2/Q6 currently lack target metadata; we’ll annotate them (`target_option`, `target_option_text`).

---

## 2. Target vs Signal Schema

| Attribute | Target Strategy | Signal Strategy |
|-----------|-----------------|-----------------|
| Applicable question types | `mcq_single`, `mcq_multi`, `true_false`, `matching` | `fill_blank`, `short_answer`, `long_answer`, `comprehension_qa` |
| Required metadata | `target_option` (letter/set), `target_option_text`, optional `target_rationale` | `signal_type` (`keyword`, `concept`, `pattern`), `signal_phrase`, optional `signal_notes` |
| Validator expectation | GPT‑4o answer should match `target_option`; deviation score derived from option change | Validator inspects response for `signal_phrase`, considers gold answer context, and outputs deviation/confidence diagnostically |
| Pipeline behavior | Mapping accepted only if GPT‑4o flips to target | Mapping retained regardless of score; diagnostics stored for analytics |

Signal design guidelines:
- **fill_blank**: supply the incorrect word/phrase that should appear post-manipulation (`signal_phrase`) plus why it’s wrong (`signal_notes`).
- **short_answer**: highlight the key misconception, providing a quote-size cue.
- **long_answer / comprehension**: describe the leading idea or factual error introduced; validator searches for mention plus divergence from gold summary.

---

## 3. GPT-5 Prompt Refresh (Conceptual)

1. **Routing**: wrapper selects `target` or `signal` instructions based on question type.
2. **Few-Shot Library**: 
   - MCQ section showcases Q2/Q6/Q8/Q9/Q10 with JSON responses including `target_option/target_option_text` and validation outcomes.
   - Signal section will source future subjective runs; for now document placeholder structure pending example capture.
3. **Hard Rules**: reiterate span constraints, option selection procedure, and metadata requirements.
4. **Strategy Hints**: list effective manipulations (negating qualifiers, swapping complexity classes, etc.) tailored per type.

---

## 4. Validation Adjustments

- Target mode: validator checks `test_answer` vs `target_option`; failure -> mapping rejected. Continue logging deviation/confidence.
- Signal mode: validator looks for `signal_phrase` (case-insensitive) and computes deviation vs gold. Output both metrics + reasoning; never auto-reject.
- Shared: persist `validation_diagnostics` block with `deviation_score`, `confidence`, `signal_detected`, `target_matched`, and raw GPT output.

---

## 5. PDF Creation Resilience

### Current Abort Point
- `PdfCreationService._generate_pdfs` raises `ValueError("PDF creation blocked: All questions must have at least one mapping.")` via `_all_questions_have_mappings`.

### Planned Changes
1. Replace hard block with per-question status tracking:
   - Collect `{question_number, reason}` for missing mappings (e.g., "no validated mappings", "generation failure").
   - Emit live logging + stage metadata under `manipulation_results.skipped_questions`.
2. Ensure renderers tolerate empty enhanced mappings (already supported but verify `build_mapping_from_questions`).
3. Scan other pipeline checkpoints (smart_substitution, orchestrator) for similar early exits and add TODOs to convert them into logged skips.

---

## 6. High-Priority Tasks

1. **MCQ Prompt Exemplars** – finalize the five examples, annotate targets, and embed in GPT‑5 generation prompt. *(Owner: next coding pass)*
2. **Signal Prompt Blueprint** – define template + pending example capture for subjective types.
3. **Metadata Schema Update** – extend mapping records (DB + structured.json) to store `target_option_text`, `signal_*` fields.
4. **Validator Refactor** – branch logic for target vs signal, keep shared diagnostics.
5. **PDF Resilience Patch** – downgrade `_all_questions_have_mappings` failure to soft skip with persisted logs.
6. **Abort Audit Follow-up** – inventory other raises (e.g., `SmartSubstitutionService` generation failures) and plan graceful handling.

---

## Open Questions / TODOs

- Capture authoritative signal examples from a subjective run to populate the few-shot library.
- Decide how to handle multi-select targets (store sorted list vs joined string).
- Confirm where skip metadata should surface in the UI.
- Review remaining `raise ValueError` sites in `smart_substitution_service.py` for future resilience work.


### Prompt Structure Sketch

```jsonc
{
  "instructions": [
    "Select strategy based on question_type (target vs signal)",
    "Follow safe-span constraints and provide required metadata"
  ],
  "few_shots": {
    "mcq_single": [
      {
        "stem_excerpt": "If T(n) = 5n^3 + 4n + 1…",
        "gold": "B",
        "mapping": {
          "original": "the correct",
          "replacement": "nsquared times the",
          "start_pos": 46,
          "end_pos": 56,
          "context": "question_stem",
          "target_option": "D",
          "target_option_text": "O(n^5)",
          "target_rationale": "New phrasing aligns with highest polynomial"
        }
      },
      {
        "stem_excerpt": "When an array is already sorted…",
        "gold": "B",
        "mapping": {
          "original": "already",
          "replacement": "not",
          "start_pos": 14,
          "end_pos": 21,
          "context": "question_stem",
          "target_option": "A",
          "target_option_text": "Selection Sort"
        }
      }
      // … Q8, Q9, Q10 similar entries
    ],
    "signal_template": {
      "fields": ["signal_type", "signal_phrase", "signal_notes"],
      "example": {
        "stem_excerpt": "Explain why gradient clipping…",
        "mapping": {
          "original": "benefit",
          "replacement": "risk",
          "signal_type": "keyword",
          "signal_phrase": "risk of gradient clipping",
          "signal_notes": "Tutor answer should warn about damping" }
      }
    }
  }
}
```

Validator prompt will mirror the same routing, injecting either `target_option` or `signal_*` metadata into the analysis instructions.


### Abort-Point Inventory (Initial Pass)

| Location | Condition | Current Behavior | Notes |
|----------|-----------|------------------|-------|
| `pdf_creation_service._all_questions_have_mappings` | Any question missing validated mapping | Raises `ValueError` and aborts stage | Needs conversion to soft skip + logged reason (priority) |
| `smart_substitution_service.auto_generate_for_question` | Upstream data missing (`question_dict`, `question_model`, `stem`) | Raises `ValueError` | Occurs before pdf stage; consider soft-failing per question in later pass |
| `smart_substitution_service._validate_candidate_mapping` | After retries, no candidate succeeds | Raises `ValueError("Auto-generated mappings failed validation…")` | For now, capture reason in mapping log; long-term we can downgrade |
| `base_renderer` helper methods | Span alignment failures | Raise `ValueError` to caller | Currently caught inside renderers; monitor when adjusting resilience |
| `pipeline_orchestrator` | Stage raises `StageExecutionFailed` | Propagates failure status | Expected; no change but we’ll ensure our stage no longer throws |

Next audit pass will catalogue additional non-mapping-related aborts (e.g., resume service) but the priority change is pdf_creation gating.

