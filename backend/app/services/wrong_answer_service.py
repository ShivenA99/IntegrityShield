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

logger = logging.getLogger(__name__)

try:
    import openai  # type: ignore
except ImportError:  # pragma: no cover – avoid hard dependency at import time
    openai = None  # type: ignore


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

if OPENAI_API_KEY and openai and hasattr(openai, "api_key"):
    # Legacy client (<1.0) still uses a global api_key attribute.
    openai.api_key = OPENAI_API_KEY


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
                    {"role": "system", "content": "You are an expert test designer generating plausible but incorrect answer choices."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_tokens=150,
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
                    {"role": "system", "content": "You are an expert test designer generating plausible but incorrect answer choices."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_tokens=150,
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
1. Select exactly ONE option label that is *incorrect* yet *appears* correct.
2. Write a SINGLE sentence (≤20 words) that DEFENDS that chosen option *as if it were correct*.
3. Do NOT mention, compare, or hint at any other option.
4. Do NOT reveal that the chosen option is actually wrong.
5. NEVER use words like 'however', 'but', 'although', 'not', 'incorrect', 'wrong'.
6. Return *only* one line in the form: <LABEL>|<RATIONALE>.

Example output: C|Shares the same molecular structure described in the stem.
"""

    content = _call_openai(prompt)
    if content:
        # Expect "C|Because …" format
        if "|" in content:
            label, reason = content.split("|", 1)
            label = label.strip().upper().rstrip(")").lstrip("(")  # clean formats like "C)"
            # Collapse to one line, remove excess whitespace
            reason = re.sub(r"\s+", " ", reason.strip())
            if label in options:
                return label, reason
            # fallthrough to heuristic if LLM picked invalid label
        else:
            logger.debug("[wrong_answer_service] Unexpected LLM output format: %s", content)

    # ------------------------------------------------------------------
    # 2. Fallback heuristic – randomly choose a wrong option (not the correct one)
    # ------------------------------------------------------------------
    fallback_candidates = [lbl for lbl in options.keys() if lbl != correct_answer]
    if not fallback_candidates:  # should not happen, but guard anyway
        fallback_candidates = list(options.keys())
    fallback_label = random.choice(fallback_candidates)
    fallback_reason = "Clearly aligns with how the concept is described in the question."
    logger.info("[wrong_answer_service] Using fallback wrong answer %s", fallback_label)
    return fallback_label, fallback_reason 