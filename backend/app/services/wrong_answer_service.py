from __future__ import annotations

"""Service to generate plausible but incorrect answers & supporting reasoning for a given MCQ question.

This module relies on the `openai` package when an ``OPENAI_API_KEY`` environment variable
is available.  If the key (or the package) is missing, a deterministic fallback strategy is
used so that the rest of the pipeline can continue to work during local testing or CI.
"""

import os
import json
import logging
import random
import re
from typing import Dict, Tuple, List
from typing import Any
from .attack_service import AttackType
from .code_glyph_entity_service import (
    generate_entities_for_question as cg_generate_entities,
    generate_entities_for_structured_question as cg_generate_structured_entities,
)

logger = logging.getLogger(__name__)

try:
    import openai  # type: ignore
except ImportError:  # pragma: no cover – avoid hard dependency at import time
    openai = None  # type: ignore


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if OPENAI_API_KEY and openai and hasattr(openai, "api_key"):
    # Legacy client (<1.0) still uses a global api_key attribute.
    openai.api_key = OPENAI_API_KEY

# Tokens to avoid choosing as input entities (too low-signal for reliable mapping)
_FORBIDDEN_INPUT_TOKENS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in",
    "and", "or", "for", "with", "on", "by", "which", "what"
}


def _call_openai(prompt: str) -> str | None:
    """Return assistant message using whichever OpenAI-Python interface is available.

    Supports *both* the legacy <1.0 methods (`openai.ChatCompletion.create`) and the
    new ≥1.0 client class (`OpenAI().chat.completions.create`).  Any error is logged
    and the function returns ``None`` so that callers can fall back gracefully.
    """

    if not (OPENAI_API_KEY and openai):
        logger.info("[wrong_answer_service] Skipping OpenAI call – OPENAI_API_KEY missing or openai package not installed.")
        return None

    try:
        # ------------------------------------------------------------------
        # 1. Prefer the >=1.0 client (OpenAI class).  This import fails on <1.0.
        # ------------------------------------------------------------------
        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert assessment designer. You must first solve questions correctly, then design minimal glyph-mapping edits that make a specific wrong option appear correct."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=500,
            )

            content: str | None = resp.choices[0].message.content  # type: ignore[attr-defined]
            return str(content).strip() if content else None
        except Exception as exc_new:
            # Either we're on the legacy client (import error) or runtime failed – log & fall through.
            logger.debug("[wrong_answer_service] >=1.0 client path failed – %s", exc_new)

        # ------------------------------------------------------------------
        # 2. Legacy <1.0 style – uses ChatCompletion global.
        # ------------------------------------------------------------------
        try:
            resp = openai.ChatCompletion.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert assessment designer. You must first solve questions correctly, then design minimal glyph-mapping edits that make a specific wrong option appear correct."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=500,
            )

            content = (
                resp["choices"][0]["message"]["content"]
                if isinstance(resp, dict)
                else resp.choices[0].message.content  # type: ignore[attr-defined]
            )
            return str(content).strip() if content else None
        except Exception as exc_legacy:
            logger.debug("[wrong_answer_service] Legacy client path failed – %s", exc_legacy)

        # If we reach here, both methods failed.
        raise RuntimeError("OpenAI call failed in both new and legacy client paths.")

    except Exception as exc:  # broad – we just want to log & continue
        logger.warning("[wrong_answer_service] Falling back after OpenAI error – %s", exc)
        return None


def _extract_json_block(raw: str) -> dict | None:
    """Extract a JSON object from raw LLM content (tolerates code fences)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        try:
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1 :]
            if text.endswith("````"):
                text = text[:-4]
            elif text.endswith("```"):
                text = text[:-3]
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# The signature now accepts *correct_answer* so callers can provide context
# (when an answer-key PDF was supplied).  This helps the LLM avoid accidentally
# choosing the right option.  The parameter is *optional* so existing callers
# remain compatible.


def generate_wrong_answer(
    stem_text: str,
    options: Dict[str, str],
    correct_answer: str | None = None,
) -> Tuple[str, str]:
    """Return a tuple ``(wrong_option_label, wrong_reason)``.

    The implementation prefers calling the OpenAI API for a more *plausible* choice, but
    falls back to a deterministic local heuristic when that is not possible.
    """
    # ------------------------------------------------------------------
    # 1. Attempt LLM-based generation
    # ------------------------------------------------------------------
    joined_opts = "\n".join(f"{label}) {text}" for label, text in options.items())

    extra_note = (
        f"\n\nNOTE: The correct answer is {correct_answer}).  Do *not* choose this one." if correct_answer else ""
    )

    prompt = f"""
You are crafting *distractors* for a multiple-choice exam.

Question: {stem_text}

Options (verbatim):
{joined_opts}{extra_note}

INSTRUCTIONS (follow *all*):
1. Select exactly ONE OR MANY option label that is *incorrect* yet *appears* correct.
2. Write a SINGLE sentence (≤20 words) that DEFENDS that chosen option *as if it were correct*.
3. Do NOT mention, compare, or hint at any other option.
4. Do NOT reveal that the chosen option is actually wrong.
5. NEVER use words like 'however', 'but', 'although', 'not', 'incorrect', 'wrong'.
6. Return *only* one line in the form: <LABEL>|<RATIONALE>.

Example output: C|Shares the same molecular structure described in the stem.
"""

    content = _call_openai(prompt)
    if content:
        # Normalize to single line for easier parsing
        one_line = re.sub(r"\s+", " ", content.strip())

        # Expect strict "C|Because …" format first
        if "|" in one_line:
            label, reason = one_line.split("|", 1)
            label = label.strip().upper().rstrip(")").lstrip("(")
            reason = re.sub(r"\s+", " ", reason.strip())
            if label in options:
                return label, reason
            # If model returned something like "B)" or "Answer: B", try to clean again below

        # Heuristic parsing for common variants:
        # - "Answer: B) ..." -> B
        # - "B) Because ..." -> B
        # - "True" / "False" when options are T/F
        # - Any token that matches an existing option key (case-insensitive)
        # Try letter options first
        letter_match = re.search(r"\b([A-D])\)?\b", one_line, flags=re.IGNORECASE)
        if letter_match:
            candidate = letter_match.group(1).upper()
            if candidate in options:
                return candidate, "Clearly aligns with how the concept is described in the question."

        # Try to match any of the provided option keys directly (for T/F or custom labels)
        for opt_key in options.keys():
            # Case-insensitive exact word match
            if re.search(rf"\b{re.escape(str(opt_key))}\b", one_line, flags=re.IGNORECASE):
                return str(opt_key), "Clearly aligns with how the concept is described in the question."

        # If we reach here, we could not parse a usable label from LLM output
        logger.info(
            "[wrong_answer_service] Unexpected LLM output format; falling back. content=%r options=%s",
            content,
            list(options.keys()),
        )

    # ------------------------------------------------------------------
    # 2. Fallback heuristic – randomly choose a wrong option (not the correct one)
    # ------------------------------------------------------------------
    fallback_candidates = [lbl for lbl in options.keys() if lbl != correct_answer]
    if not fallback_candidates:  # should not happen, but guard anyway
        fallback_candidates = list(options.keys())
    
    # Additional safety check - if still empty, use a default
    if not fallback_candidates:
        logger.warning("[wrong_answer_service] No fallback candidates available, using default")
        fallback_candidates = ["A", "B", "C", "D"]  # Default options
    
    fallback_label = random.choice(fallback_candidates)
    fallback_reason = "Clearly aligns with how the concept is described in the question."
    logger.info("[wrong_answer_service] Using fallback wrong answer %s", fallback_label)
    return fallback_label, fallback_reason



# ---------------------------------------------------------------------------
# CODE_GLYPH: Entities + wrong answer JSON
# ---------------------------------------------------------------------------

def _detect_question_type(options: Dict[str, str], stem_text: str) -> str:
    """Heuristic detection: 'true_false' | 'mcq' | 'short_answer'."""
    opt_values = " ".join(v.lower() for v in options.values())
    has_tf = ("true" in opt_values and "false" in opt_values) or ("i) true" in opt_values or "ii) false" in opt_values)
    if has_tf:
        return "true_false"
    if options:
        return "mcq"
    return "short_answer"


def _true_false_value_to_label(options: Dict[str, str], value: str) -> str | None:
    """Return the option label whose text is (True|False). Case-insensitive."""
    want = value.strip().lower()
    for lbl, txt in options.items():
        if txt.strip().lower() in {want, f"{want}.", f"{want}!", f"{want}?"}:
            return lbl
    return None


def generate_wrong_answer_entities(
    stem_text: str,
    options: Dict[str, str],
    correct_answer: str | None = None,
) -> Dict[str, str]:
    """Return a JSON-like dict suitable for CODE_GLYPH mapping.

    Keys:
      - input_entity: semantic token to encode in glyphs
      - output_entity: visual token to display
      - wrong_label: chosen wrong option label for MCQ/TF/etc.
      - rationale: short sentence defending the wrong choice
      - entity_type: "label" | "text" (how to interpret entities)
      - entity_source: "options" | "stem" (where entities came from)
      - question_type: "mcq" | "true_false" | "short_answer"
      - transformation: "negation" | "substitution" | "topic_preserving_substitution"
    """
    # Build a prompt aligned with our earlier flow
    joined_opts = "\n".join(f"{lbl}) {txt}" for lbl, txt in options.items())
    qtype = _detect_question_type(options, stem_text)

    # We deliberately avoid relying on external correct answers.
    # If a correct answer is provided, the model may use it, but it MUST still infer and return its own view.
    extra_note = ""

    # Type-aware inline guidance
    specifics = ""
    if qtype == "true_false":
        specifics = (
            "- True/False: transformation=\"negation\". Flip truth minimally (negator, quantifier, comparator) so truth switches to the wrong value.\n"
        )
    elif qtype == "short_answer":
        specifics = (
            "- Short Answer: transformation=\"topic_preserving_substitution\". Replace a central term while keeping the topic.\n"
        )
    else:
        specifics = (
            "- MCQ: transformation=\"substitution\". Align output_entity with a distinctive term from the chosen wrong option.\n"
        )

    # Few-shot exemplars (one per type, concise)
    few_shots = (
        "Example MCQ:\n"
        "Stem: Which component handles input sequence encoding?\n"
        "Options:\nA) Encoder\nB) Decoder\nC) Optimizer\nD) Loss\n"
        "JSON: {\n  \"input_entity\": \"encoding\",\n  \"output_entity\": \"decoding\",\n  \"wrong_label\": \"B\",\n  \"rationale\": \"Swaps role to match Decoder.\",\n  \"entity_type\": \"text\",\n  \"entity_source\": \"stem\",\n  \"question_type\": \"mcq\",\n  \"transformation\": \"substitution\",\n  \"inferred_correct_label\": \"A\",\n  \"inferred_correct_text\": \"Encoder\",\n  \"input_start\": 41,\n  \"input_end\": 49\n}\n\n"
        "Example True/False:\n"
        "Stem: The softmax outputs are probabilities that sum to 1.\n"
        "Options:\nA) True\nB) False\n"
        "JSON: {\n  \"input_entity\": \"sum to 1\",\n  \"output_entity\": \"do not sum to 1\",\n  \"wrong_label\": \"B\",\n  \"rationale\": \"Negates the property, flipping truth.\",\n  \"entity_type\": \"text\",\n  \"entity_source\": \"stem\",\n  \"question_type\": \"true_false\",\n  \"transformation\": \"negation\",\n  \"inferred_correct_label\": \"A\",\n  \"inferred_correct_text\": \"True\",\n  \"input_start\": 40,\n  \"input_end\": 48\n}\n\n"
        "Example Short Answer:\n"
        "Stem: What loss is used for multi-class classification?\n"
        "Options: (none)\n"
        "JSON: {\n  \"input_entity\": \"cross-entropy\",\n  \"output_entity\": \"mean squared error\",\n  \"wrong_label\": \"\",\n  \"rationale\": \"Plausible alternative within topic.\",\n  \"entity_type\": \"text\",\n  \"entity_source\": \"stem\",\n  \"question_type\": \"short_answer\",\n  \"transformation\": \"topic_preserving_substitution\",\n  \"inferred_correct_label\": \"\",\n  \"inferred_correct_text\": \"cross-entropy\",\n  \"input_start\": 0,\n  \"input_end\": 0\n}"
        )

    prompt = f"""
You will produce a glyph-mapping plan that makes a specific WRONG option appear correct by minimally altering the QUESTION text only.
 
 Return STRICT JSON only with keys:
- input_entity (string)
- output_entity (string)
- wrong_label (string)
- rationale (string <= 25 words)
- entity_type ("text")
- entity_source ("stem")
- question_type ("mcq"|"true_false"|"short_answer")
- transformation ("negation"|"substitution"|"topic_preserving_substitution")
- inferred_correct_label (string)
- inferred_correct_text (string)
- input_start (integer)
- input_end (integer)
 
Rules (ALL must hold):
1) Solve the question FIRST. Set inferred_correct_label/text.
2) Choose exactly one wrong_label from Options (when present) that you will make appear correct.
3) You may only alter the Question text: replace input_entity → output_entity in the stem. Do NOT change options.
4) input_entity MUST be a literal, contiguous substring of the stem (not from options).
5) Avoid function words. NEVER use any of: {sorted(_FORBIDDEN_INPUT_TOKENS)}.
   Prefer domain terms, numbers, units, named entities, or key adjectives/verbs.
6) Keep the change minimal but decisive: after replacement, the stem must support wrong_label and contradict inferred_correct_label.
7) {specifics}
8) Validate before returning: wrong_label ∈ labels (if any); wrong_label ≠ inferred_correct_label; input_entity length 3–30 and differs from output_entity; input_start/input_end slice input_entity from the stem.

Return ONLY the JSON object. No explanations or code fences.
 
Question (stem):
{stem_text}
 
Options (verbatim; may be empty):
 {joined_opts}
 
{few_shots}
"""

    content = _call_openai(prompt)
    if content:
        obj = _extract_json_block(content)
        if isinstance(obj, dict):
            # Basic validation
            inp = str(obj.get("input_entity", "")).strip()
            out = str(obj.get("output_entity", "")).strip()
            wlbl = str(obj.get("wrong_label", "")).strip().upper().rstrip(")").lstrip("(")
            rationale = str(obj.get("rationale", "")).strip()
            entity_type = (obj.get("entity_type") or "text").strip()
            entity_source = (obj.get("entity_source") or "stem").strip()
            question_type = (obj.get("question_type") or qtype).strip()
            transformation = (obj.get("transformation") or ("negation" if qtype == "true_false" else ("topic_preserving_substitution" if qtype == "short_answer" else "substitution"))).strip()
            inferred_label_raw = str(obj.get("inferred_correct_label", "")).strip()
            inferred_text = str(obj.get("inferred_correct_text", "")).strip()

            # Optional spans
            def _to_int(val):
                try:
                    return int(val)
                except Exception:
                    return None
            input_start = _to_int(obj.get("input_start"))
            input_end = _to_int(obj.get("input_end"))
            output_start = _to_int(obj.get("output_start"))
            output_end = _to_int(obj.get("output_end"))

            # Enforce/salvage wrong_label validity if options are present
            if options:
                if wlbl not in options:
                    # 1) try mapping by option text equality (case-insensitive)
                    low = wlbl.lower()
                    for lbl, txt in options.items():
                        if txt.strip().lower() == low:
                            wlbl = lbl
                            break
                    # 2) if still not found, try T/F mapping
                    if wlbl not in options:
                        tf_lbl = _true_false_value_to_label(options, wlbl)
                        if tf_lbl:
                            wlbl = tf_lbl
                    # 3) last resort: extract a single-letter label from content
                    if wlbl not in options:
                        m = re.search(r"\b([A-Z])\b", (out or "") + "\n" + (content or ""))
                        if m and m.group(1) in options:
                            wlbl = m.group(1)
                # Map inferred correct label to an option label if present
                inferred_label = inferred_label_raw
                if inferred_label and inferred_label not in options:
                    low_inf = inferred_label.lower()
                    # by text equality
                    for lbl, txt in options.items():
                        if txt.strip().lower() == low_inf:
                            inferred_label = lbl
                            break
                    if inferred_label not in options:
                        tf_inf = _true_false_value_to_label(options, inferred_label)
                        if tf_inf:
                            inferred_label = tf_inf
                    if inferred_label not in options and len(inferred_label) == 1 and inferred_label.upper() in options:
                        inferred_label = inferred_label.upper()
                else:
                    inferred_label = inferred_label_raw
                if correct_answer and wlbl == correct_answer:
                    # pick an alternative
                    alts = [k for k in options.keys() if k != correct_answer]
                    wlbl = alts[0] if alts else (wlbl or "A")
                # Ensure wrong_label != inferred correct when we have an inference
                if options and inferred_label and wlbl == inferred_label:
                    alts = [k for k in options.keys() if k != inferred_label]
                    if alts:
                        wlbl = alts[0]

            # Additional semantic validation of input_entity
            inp_lc = inp.lower()
            if inp_lc in _FORBIDDEN_INPUT_TOKENS or len(inp) < 3 or len(inp) > 30:
                logger.info("[wrong_answer_service] Rejecting low-signal input_entity from LLM: %r", inp)
                inp = ""

            # Validate required fields: input_entity must be a stem substring; wrong_label required when options exist
            if inp and out and ((not options) or wlbl) and (inp in stem_text):
                # If indices provided, verify they slice the same substring
                if input_start is not None and input_end is not None:
                    try:
                        if stem_text[input_start:input_end] != inp:
                            logger.info("[wrong_answer_service] Provided indices do not match input_entity; dropping indices.")
                            input_start = None
                            input_end = None
                    except Exception:
                        input_start = None
                        input_end = None
                result = {
                    "input_entity": inp,
                    "output_entity": out,
                    "wrong_label": wlbl,
                    "rationale": rationale or "Clearly aligns with phrasing in the question.",
                    "entity_type": entity_type,
                    "entity_source": entity_source,
                    "question_type": question_type,
                    "transformation": transformation,
                    "inferred_correct_label": inferred_label if options else "",
                    "inferred_correct_text": inferred_text,
                }
                if input_start is not None and input_end is not None:
                    result["input_start"] = input_start
                    result["input_end"] = input_end
                logger.info("[wrong_answer_service] CODE_GLYPH entities: %s", result)
                return result
        logger.info("[wrong_answer_service] Unexpected JSON for CODE_GLYPH; content=%r", content)

    # Fallback heuristic (substring-based from question stem)
    # Pick two distinct alphanumeric tokens from the question text as input/output entities
    tokens = re.findall(r"[A-Za-z0-9]{3,}", stem_text)
    # Filter out forbidden tokens
    tokens = [t for t in tokens if t.lower() not in _FORBIDDEN_INPUT_TOKENS]
    if not tokens:
        tokens = [stem_text[:3]] if len(stem_text) >= 3 else [stem_text]
    input_entity = tokens[0]
    output_entity = tokens[1] if len(tokens) > 1 else tokens[0]
    if output_entity == input_entity and len(tokens[0]) >= 4:
        output_entity = tokens[0][: len(tokens[0]) - 1]

    # Choose an available wrong label not equal to correct_answer
    candidates = [k for k in options.keys() if k != correct_answer] or list(options.keys()) or ["C"]
    wrong_label = candidates[0]

    question_type = _detect_question_type(options, stem_text)
    transformation = "negation" if question_type == "true_false" else ("topic_preserving_substitution" if question_type == "short_answer" else "substitution")

    result = {
        "input_entity": str(input_entity),
        "output_entity": str(output_entity),
        "wrong_label": str(wrong_label),
        "rationale": "Appears consistent with the question phrasing without revealing it is incorrect.",
        "entity_type": "text",
        "entity_source": "stem",
        "question_type": question_type,
        "transformation": transformation,
        "inferred_correct_label": (correct_answer or (next((k for k in options.keys() if k != wrong_label), "")) if options else ""),
        "inferred_correct_text": (options.get(correct_answer) if (options and correct_answer in options) else (options.get(next((k for k in options.keys() if k != wrong_label), ""), "") if options else "")),
    }
    logger.warning("[wrong_answer_service] Using fallback CODE_GLYPH entities: %s", result)
    return result 


def generate_wrong_answer_for_question(question: Dict[str, Any], attack_type: AttackType, ocr_doc: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Generate wrong answer data per (attack_type, q_type) using full structured question payload.

    Returns a dict that may include keys depending on q_type and attack_type, e.g.:
      - wrong_label, wrong_labels, wrong_answer, wrong_reason
      - target_wrong_mapping (for match)
      - code_glyph_entities (for CODE_GLYPH)
    """
    q_type = (question.get("q_type") or "").strip()
    stem_text = question.get("stem_text") or ""
    options: Dict[str, str] = question.get("options") or {}
    matches: List[Dict[str, str]] = question.get("matches") or []
    blanks: List[Dict[str, str]] = question.get("blanks") or []

    # Prevention: nothing to generate
    if attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION:
        return {}

    # Hidden malicious (detection): create a wrong answer + reason
    if attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP:
        # Use LLM to infer right and then derive wrong according to q_type
        payload = {
            "q_type": q_type,
            "stem_text": stem_text,
            "options": options,
            "matches": matches,
            "blanks": blanks,
        }
        prompt = (
            "You are generating WRONG answers for adversarial exam testing. First infer the RIGHT answer, "
            "then output a WRONG answer with a concise wrong_reason. Return JSON only.\n\n"
            f"Question JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            "Output schemas by q_type:\n"
            "- mcq_single: {\"right\": \"B\", \"wrong\": \"D\", \"wrong_reason\": \"...\"}\n"
            "- mcq_multi: {\"right\": [\"A\",\"C\"], \"wrong\": [\"A\",\"B\"], \"wrong_reason\": \"...\"}\n"
            "- true_false: {\"right\": \"True\", \"wrong\": \"False\", \"wrong_reason\": \"...\"}\n"
            "- match: {\"right\": [{\"L\":\"A\",\"R\":\"3\"},...], \"wrong\": [{\"L\":\"A\",\"R\":\"2\"},...], \"wrong_reason\": \"...\"}\n"
            "- fill_blank: {\"right\": \"token\", \"wrong\": \"token\", \"wrong_reason\": \"...\"}\n"
            "- short_answer/long_answer/comprehension_qa: {\"right\": \"text\", \"wrong\": \"text\", \"wrong_reason\": \"...\"}\n"
        )
        content = _call_openai(prompt)
        data: Dict[str, Any] = {}
        if content:
            obj = _extract_json_block(content) or {}
            # Normalize fields
            if q_type in {"mcq_single", "mcq_multi"}:
                right = obj.get("right")
                wrong = obj.get("wrong")
                # Coerce to lists for mcq_multi
                if q_type == "mcq_single":
                    if isinstance(wrong, str):
                        data["wrong_label"] = wrong.strip().upper().rstrip(")").lstrip("(")
                    data["wrong_reason"] = (obj.get("wrong_reason") or "Plausible but incorrect.").strip()
                else:
                    if isinstance(wrong, list):
                        data["wrong_labels"] = [str(x).strip().upper().rstrip(")").lstrip("(") for x in wrong]
                    data["wrong_reason"] = (obj.get("wrong_reason") or "Plausible but incorrect.").strip()
            elif q_type == "true_false":
                wrong = obj.get("wrong")
                data["wrong_answer"] = "True" if str(wrong).strip().lower().startswith("t") else "False"
                data["wrong_reason"] = (obj.get("wrong_reason") or "Plausible but incorrect.").strip()
            elif q_type == "match":
                wrong = obj.get("wrong") or []
                # Expect list of {L,R}
                if isinstance(wrong, list):
                    data["target_wrong_mapping"] = [{"L": str(p.get("L", "")), "R": str(p.get("R", ""))} for p in wrong]
                data["wrong_reason"] = (obj.get("wrong_reason") or "Plausible but incorrect.").strip()
            else:
                # fill_blank / short_answer / long_answer / comprehension_qa
                data["wrong_answer"] = obj.get("wrong") or ""
                data["wrong_reason"] = (obj.get("wrong_reason") or "Plausible but incorrect.").strip()
        # If parsing failed, provide a minimal fallback
        if not data:
            if q_type in {"mcq_single", "mcq_multi"} and options:
                labels = list(options.keys())
                data = {"wrong_label": (labels[1] if len(labels) > 1 else labels[0]), "wrong_reason": "Plausible but incorrect."}
            elif q_type == "true_false":
                data = {"wrong_answer": "False", "wrong_reason": "Plausible but incorrect."}
            elif q_type == "match" and matches:
                # Simple rotate of rights
                right_rs = [m.get("right", "") for m in matches]
                rotated = right_rs[1:] + right_rs[:1]
                data = {"target_wrong_mapping": [{"L": m.get("left", ""), "R": rotated[i]} for i, m in enumerate(matches)], "wrong_reason": "Plausible but incorrect."}
            else:
                data = {"wrong_answer": "", "wrong_reason": "Plausible but incorrect."}
        return data

    # CODE_GLYPH: build entities with per-type strategy
    if attack_type == AttackType.CODE_GLYPH:
        # Unified structured-entity generator handles all q_types and returns target_wrong or target_wrong_mapping
        ent_struct = cg_generate_structured_entities(question)
        return {"code_glyph_entities": ent_struct}

    # Default no-op
    return {} 


 