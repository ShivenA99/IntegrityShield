from __future__ import annotations

import json
import logging
import os
from typing import Dict, Any, List

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
            max_tokens=700,
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
            max_tokens=700,
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


# New: full structured-question path spanning all q_types

def generate_entities_for_structured_question(question: Dict[str, Any]) -> Dict[str, Any]:
    """Return minimal glyph entities plus a target_wrong suitable for all q_types.

    Output contract by q_type:
      - mcq_single/mcq_multi/true_false:
        { "entities": {"input_entity": str, "output_entity": str}, "target_wrong": "D" | ["A","B"] }
      - match:
        { "entities": [{"input_entity": str, "output_entity": str}, ...], "target_wrong_mapping": [{"L": str, "R": str}, ...] }
      - fill_blank:
        { "entities": {"input_entity": str, "output_entity": str}, "target_wrong": str }
      - short_answer/long_answer/comprehension_qa:
        { "entities": {"input_entity": str, "output_entity": str}, "target_wrong": str }
    """
    q_type = (question.get("q_type") or "").strip()
    payload = {
        "q_type": q_type,
        "stem_text": question.get("stem_text") or "",
        "options": question.get("options") or {},
        "matches": question.get("matches") or [],
        "blanks": question.get("blanks") or [],
    }

    prompt = (
        "You are designing glyph-mapping entities for a code-glyph attack.\n"
        "Task: FIRST infer the RIGHT answer for the question. THEN propose a TARGET WRONG answer.\n"
        "Finally, propose MINIMAL entity mappings that, when applied to the STEM text only, will visually steer a downstream model/human toward the TARGET WRONG.\n\n"
        "Return STRICT JSON ONLY (no prose, no backticks).\n\n"
        f"Question JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Output schemas by q_type:\n"
        "- mcq_single: {\"entities\": {\"input_entity\": \"...\", \"output_entity\": \"...\"}, \"target_wrong\": \"D\"}\n"
        "- mcq_multi: {\"entities\": {\"input_entity\": \"...\", \"output_entity\": \"...\"}, \"target_wrong\": [\"A\",\"B\"]}\n"
        "- true_false: {\"entities\": {\"input_entity\": \"...\", \"output_entity\": \"...\"}, \"target_wrong\": \"False\"}\n"
        "- match: {\"entities\": [{\"input_entity\": \"RightToken\", \"output_entity\": \"WrongToken\"}, ...], \"target_wrong_mapping\": [{\"L\":\"A\", \"R\":\"2\"}, ...]}\n"
        "- fill_blank: {\"entities\": {\"input_entity\": \"answer\", \"output_entity\": \"answer_alt\"}, \"target_wrong\": \"answer_alt\"}\n"
        "- short_answer/long_answer/comprehension_qa: {\"entities\": {\"input_entity\": \"...\", \"output_entity\": \"...\"}, \"target_wrong\": \"text\"}\n\n"
        "Rules:\n"
        "1) Entities must be literal substrings from the STEM (input_entity) and a minimal substitution (output_entity).\n"
        "2) Do not modify options; mapping must act on the STEM text only.\n"
        "3) Avoid function words; pick salient, domain-specific tokens (3–30 chars).\n"
        "4) Ensure target_wrong differs from the inferred correct answer.\n"
    )

    content = _call_openai(prompt)
    if content:
        obj = _extract_json(content) or {}
        # Basic sanity: ensure shapes
        try:
            if q_type in {"mcq_single", "mcq_multi", "true_false", "fill_blank", "short_answer", "long_answer", "comprehension_qa"}:
                ents = obj.get("entities") or {}
                ie = str(ents.get("input_entity", "")).strip()
                oe = str(ents.get("output_entity", "")).strip()
                result = {"entities": {"input_entity": ie, "output_entity": oe}}
                if q_type == "mcq_multi":
                    result["target_wrong"] = obj.get("target_wrong") or []
                else:
                    result["target_wrong"] = obj.get("target_wrong")
                if (ie and oe) and result.get("target_wrong") is not None:
                    logger.info("[code_glyph_entity_service] Structured entities: %s", result)
                    return result
            elif q_type == "match":
                entities = obj.get("entities") or []
                wrong_map = obj.get("target_wrong_mapping") or []
                if isinstance(entities, list) and isinstance(wrong_map, list):
                    norm_entities = []
                    for e in entities:
                        norm_entities.append({
                            "input_entity": str(e.get("input_entity", "")),
                            "output_entity": str(e.get("output_entity", "")),
                        })
                    norm_map = []
                    for p in wrong_map:
                        norm_map.append({"L": str(p.get("L", "")), "R": str(p.get("R", ""))})
                    result = {"entities": norm_entities, "target_wrong_mapping": norm_map}
                    logger.info("[code_glyph_entity_service] Structured match entities: %s", result)
                    return result
        except Exception as e:
            logger.info("[code_glyph_entity_service] Parsing structured entities failed: %s", e)
        logger.info("[code_glyph_entity_service] Unexpected LLM output; content=%r", content)

    # Fallbacks per type
    if q_type in {"mcq_single", "mcq_multi", "true_false"}:
        # Try simple label flip using options
        stem = question.get("stem_text") or ""
        options = question.get("options") or {}
        fallback = generate_entities_for_question(stem, options)
        fallback.update({"target_wrong": "B" if "B" in options else next(iter(options.keys()), "A")})
        return {"entities": fallback, "target_wrong": fallback["output_entity"] if q_type == "true_false" else fallback.get("target_wrong")}
    if q_type == "match":
        matches: List[Dict[str, str]] = question.get("matches") or []
        right_rs = [m.get("right", f"R{i}") for i, m in enumerate(matches)]
        rotated = right_rs[1:] + right_rs[:1]
        entities = [{"input_entity": r, "output_entity": rotated[i]} for i, r in enumerate(right_rs)]
        wrong_map = [{"L": m.get("left", f"L{i}"), "R": rotated[i]} for i, m in enumerate(matches)]
        return {"entities": entities, "target_wrong_mapping": wrong_map}
    # fill/short/long/comprehension fallback
    stem = question.get("stem_text") or ""
    tokens = [t for t in stem.split() if len(t) >= 3]
    inp = tokens[0] if tokens else "term"
    out = (tokens[1] if len(tokens) > 1 else inp + "_alt")
    return {"entities": {"input_entity": inp, "output_entity": out}, "target_wrong": out} 