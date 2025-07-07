from __future__ import annotations

"""Service for evaluating attacked questions with OpenAI's GPT-4o model.

The module expects ``OPENAI_API_KEY`` to be set in the environment.  You can
optionally override the model with ``OPENAI_EVAL_MODEL`` (defaults to
``gpt-4o-mini`` which is the public preview name as of mid-2024).
"""

import os
import logging
from typing import Dict, Any

try:
    import openai  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("The 'openai' package is required but not installed.") from exc

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_EVAL_MODEL = os.getenv("OPENAI_EVAL_MODEL", "gpt-4o-mini")

if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not set – OpenAI evaluation will be disabled.")
else:
    # Only legacy client (<1.0) still relies on global api_key
    if hasattr(openai, "api_key"):
        openai.api_key = OPENAI_API_KEY


def call_openai_eval(prompt: str) -> Dict[str, Any]:
    """Send *prompt* to GPT-4o (or configured model), return parsed data.

    The return dict mirrors the old perplexity structure::
        {"raw": <full response>, "answer_text": <assistant reply string>}.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    try:
        # 1. Try ≥1.0 client (OpenAI class)
        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=OPENAI_API_KEY)
            resp_obj = client.chat.completions.create(
                model=OPENAI_EVAL_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.2,
            )

            answer_text = resp_obj.choices[0].message.content  # type: ignore[attr-defined]
            raw_data: Any = resp_obj
            return {"raw": raw_data, "answer_text": str(answer_text).strip()}
        except Exception as exc_new:
            logger.debug("[openai_eval_service] >=1.0 client path failed – %s", exc_new)

        # 2. Fallback to legacy ChatCompletion
        try:
            resp_obj = openai.ChatCompletion.create(
                model=OPENAI_EVAL_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.2,
            )

            if hasattr(resp_obj, "to_dict_recursive"):
                raw_data = resp_obj.to_dict_recursive()  # type: ignore[attr-defined]
            else:
                raw_data = resp_obj

            answer_text = raw_data["choices"][0]["message"]["content"]  # type: ignore[index]
            return {"raw": raw_data, "answer_text": str(answer_text).strip()}
        except Exception as exc_legacy:
            logger.debug("[openai_eval_service] Legacy client path failed – %s", exc_legacy)

        raise RuntimeError("OpenAI call failed in both new and legacy client paths.")

    except Exception as exc:
        logger.error("[openai_eval_service] OpenAI call failed: %s", exc, exc_info=True)
        raise 