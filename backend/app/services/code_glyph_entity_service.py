from __future__ import annotations

import json
import logging
import os
from typing import Dict, Any, List

from .code_glyph_entity_picker import extract_formatted_tokens
import re

# Curated instruction words and same-length meaningful replacements
_INSTRUCTION_WORDS = {
    "explain", "justify", "analyze", "summarize", "describe", "compare", "contrast",
    "define", "outline", "list", "show", "prove", "argue", "discuss", "state",
}
# Same-length or near-same-length antonyms/switches (prefer equal length)
_INSTRUCTION_REPLACEMENTS = {
    "explain": ["justify"],  # 7 -> 7
    "justify": ["explain"],  # 7 -> 7
    "analyze": ["justify"],  # 7 -> 7 (semantic shift)
    "summarize": [],
    "describe": [],
    "compare": ["contrast"],  # 7 -> 8 (avoid if strict equal required)
    "contrast": ["compare"],
    "define": ["defend"],    # 6 -> 6 (semantic shift)
    "outline": [],
    "list": ["show"],        # 4 -> 4
    "show": ["list"],        # 4 -> 4
    "prove": [],
    "argue": [],
    "discuss": [],
    "state": [],
}


def _find_instruction_candidates(stem_text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z]+", stem_text or "")
    cand = []
    seen = set()
    for t in tokens[:20]:  # focus near the start
        tl = t.lower()
        if tl in _INSTRUCTION_WORDS and tl not in seen:
            seen.add(tl)
            cand.append(tl)
    return cand


def _choose_curated_replacement(instr: str) -> str | None:
    opts = _INSTRUCTION_REPLACEMENTS.get(instr.lower()) or []
    for o in opts:
        if len(o) == len(instr):
            return o
    return None


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
        "disallowed_formatted_tokens": extract_formatted_tokens(question, question.get("_ocr_doc")) if isinstance(question, dict) else [],
    }
    # Long-form guidance: prefer instruction words
    long_form_types = {"short_answer", "long_answer", "comprehension_qa"}
    instruction_candidates = _find_instruction_candidates(payload["stem_text"]) if q_type in long_form_types else []
    allowed_replacements = {}
    if instruction_candidates:
        for w in instruction_candidates:
            repl = _INSTRUCTION_REPLACEMENTS.get(w) or []
            if repl:
                allowed_replacements[w] = repl

    extra_long_form = ""
    if instruction_candidates:
        extra_long_form = (
            "Long-form preference: choose an instruction word from instruction_candidates and a meaningful same-length replacement from allowed_replacements if possible.\n\n"
            f"instruction_candidates: {json.dumps(instruction_candidates)}\n"
            f"allowed_replacements: {json.dumps(allowed_replacements)}\n\n"
        )

    prompt = (
        "You are designing glyph-mapping entities for a code-glyph attack.\n"
        "Goal: choose a minimal substring in the STEM (input_entity) and a visually similar output_entity of the SAME length to cause the reader to pick the TARGET WRONG answer.\n\n"
        "STRICT RULES:\n"
        "- input_entity MUST be an EXACT substring from the STEM text, case-sensitive, appearing EXACTLY ONCE.\n"
        "- Prefer tokens that are (a) numeric values or years, or (b) negation markers (not, never, except, least), IF changing them will plausibly flip the answer.\n"
        "- Avoid formatted words (bold/italic) and avoid punctuation-only strings. Use alphanumerics only.\n"
        "- output_entity MUST be SAME LENGTH as input_entity and a MEANINGFUL English word/phrase (no misspellings, no gibberish).\n"
        "- Do NOT modify options; mapping acts on STEM only.\n"
        "- If no safe token exists, choose the next best unique unformatted word of length 2–15.\n"
        "- Return STRICT JSON ONLY. No prose, no code fences.\n\n"
        f"Question JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"{extra_long_form}"
        "Output schemas by q_type:\n"
        "- mcq_single: {\"entities\": {\"input_entity\": \"...\", \"output_entity\": \"...\"}, \"target_wrong\": \"D\"}\n"
        "- mcq_multi: {\"entities\": {\"input_entity\": \"...\", \"output_entity\": \"...\"}, \"target_wrong\": [\"A\",\"B\"]}\n"
        "- true_false: {\"entities\": {\"input_entity\": \"...\", \"output_entity\": \"...\"}, \"target_wrong\": \"False\"}\n"
        "- match: {\"entities\": [{\"input_entity\": \"RightToken\", \"output_entity\": \"WrongToken\"}, ...], \"target_wrong_mapping\": [{\"L\":\"A\", \"R\":\"2\"}, ...]}\n"
        "- fill_blank: {\"entities\": {\"input_entity\": \"answer\", \"output_entity\": \"answer_alt\"}, \"target_wrong\": \"answer_alt\"}\n"
        "- short_answer/long_answer/comprehension_qa: {\"entities\": {\"input_entity\": \"...\", \"output_entity\": \"...\"}, \"target_wrong\": \"text\"}\n"
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
                # Enforce same length post-condition
                if ie and oe and len(ie) != len(oe):
                    oe = oe[: len(ie)]
                # Long-form: prefer instruction candidates
                if instruction_candidates and ie and ie.lower() not in instruction_candidates:
                    # Try to replace with a curated instruction if present
                    for cand in instruction_candidates:
                        repl = _choose_curated_replacement(cand)
                        if repl and len(repl) == len(cand) and cand in payload["stem_text"]:
                            ie, oe = cand, repl
                            break
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
                        _ie = str(e.get("input_entity", ""))
                        _oe = str(e.get("output_entity", ""))
                        if _ie and _oe and len(_ie) != len(_oe):
                            _oe = _oe[: len(_ie)]
                        norm_entities.append({
                            "input_entity": _ie,
                            "output_entity": _oe,
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
        entities = [{"input_entity": r, "output_entity": rotated[i][: len(r)]} for i, r in enumerate(right_rs)]
        wrong_map = [{"L": m.get("left", f"L{i}"), "R": rotated[i]} for i, m in enumerate(matches)]
        return {"entities": entities, "target_wrong_mapping": wrong_map}
    # fill/short/long/comprehension fallback
    stem = question.get("stem_text") or ""
    if q_type in long_form_types:
        instr = next((w for w in _find_instruction_candidates(stem) if _choose_curated_replacement(w)), None)
        if instr:
            repl = _choose_curated_replacement(instr) or instr
            return {"entities": {"input_entity": instr, "output_entity": repl[: len(instr)]}, "target_wrong": repl}
    tokens = [t for t in stem.split() if len(t) >= 3]
    inp = tokens[0] if tokens else "term"
    out = (tokens[1] if len(tokens) > 1 else inp + "_alt")
    out = out[: len(inp)]
    return {"entities": {"input_entity": inp, "output_entity": out}, "target_wrong": out} 