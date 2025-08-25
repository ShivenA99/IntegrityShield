from __future__ import annotations

import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
    import openai  # type: ignore
except ImportError:  # pragma: no cover
    openai = None  # type: ignore

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if OPENAI_API_KEY and openai and hasattr(openai, "api_key"):
    openai.api_key = OPENAI_API_KEY


def _call_openai(prompt: str) -> str | None:
    if not (OPENAI_API_KEY and openai):
        logger.warning("[code_glyph_entity_service] Skipping OpenAI call – OPENAI_API_KEY missing or openai not installed.")
        return None

    # Prefer new client
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        content = resp.choices[0].message.content  # type: ignore[attr-defined]
        return str(content).strip() if content else None
    except Exception as exc_new:
        logger.debug("[code_glyph_entity_service] >=1.0 client path failed – %s", exc_new)

    # Legacy fallback
    try:
        resp = openai.ChatCompletion.create(  # type: ignore
            model=OPENAI_MODEL,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        if hasattr(resp, "to_dict_recursive"):
            data = resp.to_dict_recursive()  # type: ignore[attr-defined]
        else:
            data = resp
        content = data["choices"][0]["message"]["content"]  # type: ignore[index]
        return str(content).strip() if content else None
    except Exception as exc_legacy:
        logger.debug("[code_glyph_entity_service] Legacy client path failed – %s", exc_legacy)

    return None


def _build_prompt(stem_text: str, options: Dict[str, str]) -> str:
    joined_opts = "\n".join(f"{k}) {v}" for k, v in options.items())
    return (
        "You will extract entities for a code-glyph font-mapping attack.\n"
        "Given a question and options, produce STRICT JSON with keys: input_entity, output_entity.\n"
        "Rules:\n"
        "- input_entity: the semantic string to be encoded in glyphs (what the model should parse if it reads text semantically).\n"
        "- output_entity: the visual string to be displayed (what a human or visual model perceives).\n"
        "- Return ONLY JSON. No backticks, no prose, no code fences.\n\n"
        f"Question: {stem_text}\n\n"
        f"Options:\n{joined_opts}\n\n"
        "Return example: {\"input_entity\": \"B\", \"output_entity\": \"C\"}"
    )


def _extract_json(raw: str) -> Dict[str, Any] | None:
    text = raw.strip()
    # Remove common code fences if present
    if text.startswith("```"):
        try:
            first = text.find("\n")
            if first != -1:
                text = text[first + 1 :]
            if text.endswith("```"):
                text = text[: -3]
        except Exception:
            pass
    # Try JSON parse
    try:
        return json.loads(text)
    except Exception:
        # Try to locate a JSON object substring
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None


def generate_entities_for_question(stem_text: str, options: Dict[str, str]) -> Dict[str, str]:
    """Return {"input_entity": str, "output_entity": str} for CODE_GLYPH.

    Falls back to a deterministic placeholder if LLM is unavailable.
    """
    prompt = _build_prompt(stem_text, options)
    logger.debug("[code_glyph_entity_service] Prompt: %s", prompt)

    content = _call_openai(prompt)
    if content:
        parsed = _extract_json(content)
        if isinstance(parsed, dict) and "input_entity" in parsed and "output_entity" in parsed:
            input_entity = str(parsed["input_entity"]).strip()
            output_entity = str(parsed["output_entity"]).strip()
            result = {"input_entity": input_entity, "output_entity": output_entity}
            logger.info("[code_glyph_entity_service] Entities extracted: %s", result)
            return result
        logger.info("[code_glyph_entity_service] Unexpected LLM output; content=%r", content)

    # Fallback
    fallback = {"input_entity": "B", "output_entity": "C"}
    logger.warning("[code_glyph_entity_service] Using fallback entities: %s", fallback)
    return fallback 