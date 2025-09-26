from __future__ import annotations

import json
import logging
import os
from typing import Dict, Any, List, Optional

from .entity_picker import extract_formatted_tokens
import re
from ....llm.prompts.code_glyph_prompts import build_long_form_prompt, build_structured_v2_prompt

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
    """Low level helper to call OpenAI chat completions and return .content text.

    Supports *both* the legacy <1.0 methods (`openai.ChatCompletion.create`) and the
    new ≥1.0 client class (`OpenAI().chat.completions.create`).  Any error is logged
    and returns None.
    """
    try:
        logger.info("[code_glyph_entity_service] Calling OpenAI with prompt (first 400 chars): %s", (prompt or "")[:400])
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
        )
        logger.debug("[code_glyph_entity_service] Raw generation response (new client): %s", resp)
        content = resp.choices[0].message.content if resp and resp.choices else None
        if content:
            logger.info("[code_glyph_entity_service] OpenAI content (first 400 chars): %s", str(content)[:400])
        return content.strip() if content else None
    except Exception as e_new:
        logger.debug("[_call_openai] new client path failed: %s", e_new)

    try:
        resp = openai.ChatCompletion.create(  # type: ignore
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
        )
        raw = resp.to_dict_recursive() if hasattr(resp, "to_dict_recursive") else resp
        logger.debug("[code_glyph_entity_service] Raw generation response (legacy): %s", raw)
        content = raw["choices"][0]["message"]["content"] if raw else None
        if content:
            logger.info("[code_glyph_entity_service] OpenAI content (first 400 chars): %s", str(content)[:400])
        return (content or "").strip() or None
    except Exception as e_legacy:
        logger.error("[_call_openai] legacy path failed: %s", e_legacy)
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
    logger.info("[code_glyph_entity_service] Prompt (first 400 chars): %s", prompt[:400])

    content = _call_openai(prompt)
    if content:
        logger.info("[code_glyph_entity_service] Response (first 400 chars): %s", content[:400])
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


def _tokenize_alnum(s: str) -> List[str]:
    try:
        return re.findall(r"[A-Za-z0-9]+", s or "")
    except Exception:
        return []


def _compute_repeated_tokens(stem_text: str) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for t in _tokenize_alnum(stem_text):
        tl = t.lower()
        counts[tl] = counts.get(tl, 0) + 1
    return [{"token": k, "count": v} for k, v in counts.items() if v > 1]


def generate_structured_entities_v2(question: Dict[str, Any]) -> Dict[str, Any]:
    """V2: Solve→Edit→Simulate with strict anchoring and visual≥parsed enforcement.

    Input: question dict with fields:
      - q_type, stem_text, options, matches, blanks, correct_answer (optional), _ocr_doc (optional)

    Returns (backward-compatible minimal fields plus extras when present):
      - { "entities": {"input_entity": visual, "output_entity": parsed}, "target_wrong": ..., "anchor": {...}, ... }
    """
    q_type = (question.get("q_type") or "").strip()
    stem_text: str = question.get("stem_text") or ""
    options: Dict[str, str] = question.get("options") or {}
    correct_answer = question.get("correct_answer") or question.get("gold_answer") or None
    matches = question.get("matches") or []

    disallowed = extract_formatted_tokens(question, question.get("_ocr_doc")) if isinstance(question, dict) else []
    repeated = _compute_repeated_tokens(stem_text)

    payload = {
        "q_type": q_type,
        "stem_text": stem_text,
        "options": options,
        "correct_answer": ({"label": str(correct_answer), "text": options.get(str(correct_answer), "")} if correct_answer else None),
        "disallowed_formatted_tokens": disallowed,
        "repeated_token_inventory": repeated,
        "match_pairs": ([{"L": m.get("left", ""), "R": m.get("right", "")} for m in matches] if q_type == "match" else None),
    }

    # Build prompt v2 via centralized builder
    prompt = build_structured_v2_prompt(question)

    logger.debug("[code_glyph_entity_service] V2 prompt: %s", prompt)
    content = _call_openai(prompt)
    if not content:
        raise RuntimeError("LLM returned no content for v2")

    obj = _extract_json(content) or {}

    def _enforce_lengths(v: str, p: str) -> tuple[str, str]:
        v = (v or "").strip()
        p = (p or "").strip()
        if len(v) >= len(p):
            return v, p
        # Truncate parsed to visual length to enforce visual≥parsed
        return v, p[: len(v)]

    def _unique_idx(hay: str, needle: str) -> int:
        try:
            first = hay.find(needle)
            if first == -1:
                return -1
            second = hay.find(needle, first + 1)
            if second != -1:
                return -2  # non-unique
            return first
        except Exception:
            return -1

    result: Dict[str, Any] = {}

    if q_type == "match":
        ents = obj.get("entities") or []
        wrong_map = obj.get("target_wrong_mapping") or []
        norm_entities = []
        if isinstance(ents, list):
            for e in ents:
                v = str(e.get("visual_entity", ""))
                p = str(e.get("parsed_entity", ""))
                v, p = _enforce_lengths(v, p)
                # For match, allow non-alnum tokens (e.g., SHA-256). Just enforce non-identity.
                if v == p or not v:
                    raise RuntimeError("V2 identity or empty entity not allowed (match)")
                norm_entities.append({"input_entity": v, "output_entity": p, "side": e.get("side"), "pair_index": e.get("pair_index"), "anchor": e.get("anchor")})
        result = {"entities": norm_entities, "target_wrong_mapping": [{"L": str(m.get("L", "")), "R": str(m.get("R", ""))} for m in (wrong_map if isinstance(wrong_map, list) else [])]}
        return result

    # All other types operate on stem_text
    ents = obj.get("entities") or {}
    v = str(ents.get("visual_entity", ""))
    p = str(ents.get("parsed_entity", ""))
    v, p = _enforce_lengths(v, p)

    # Enforce single-token alphanumeric and non-identity for non-match
    if (not v) or (v == p) or (" " in v) or (not v.isalnum()):
        raise RuntimeError("V2 invalid entity: require single alphanumeric visual token, non-identity, visual>=parsed")

    anchor = obj.get("anchor") or {}
    try:
        cs = int(anchor.get("char_start"))
        ce = int(anchor.get("char_end"))
    except Exception:
        cs = -1; ce = -1

    # Validate anchor against stem_text; if invalid, attempt to auto-correct by unique search
    if 0 <= cs < ce <= len(stem_text) and stem_text[cs:ce] == v:
        pass
    else:
        idx = _unique_idx(stem_text, v)
        if idx >= 0:
            cs, ce = idx, idx + len(v)
        else:
            # Hard failure: cannot anchor uniquely
            raise RuntimeError("V2 entity anchor validation failed")

    result = {
        "entities": {"input_entity": v, "output_entity": p},
        "anchor": {"char_start": cs, "char_end": ce, "anchor_text": stem_text[cs:ce]},
    }

    # target_wrong normalization
    if q_type == "mcq_multi":
        tw = obj.get("target_wrong") or []
        if isinstance(tw, list):
            result["target_wrong"] = [str(x).strip().upper().rstrip(")").lstrip("(") for x in tw]
    elif q_type == "mcq_single":
        tw = obj.get("target_wrong")
        if isinstance(tw, str):
            result["target_wrong"] = tw.strip().upper().rstrip(")").lstrip("(")
    elif q_type == "true_false":
        tw = obj.get("target_wrong")
        if isinstance(tw, str):
            val = tw.strip().lower()
            result["target_wrong"] = "True" if val.startswith("t") else "False"
    else:
        # fill/short/long/comprehension
        result["target_wrong"] = obj.get("target_wrong")

    # Carry through optional diagnostics
    for k in ("baseline_inference", "after_inference", "flip_validated", "transformation", "evidence_tokens"):
        if k in obj:
            result[k] = obj.get(k)

    logger.info("[code_glyph_entity_service] V2 entities: %s", {k: (v if k != "entities" else result["entities"]) for k, v in result.items() if k in {"entities", "target_wrong"}})
    return result 


def _is_single_alnum(token: str) -> bool:
    return bool(token) and token.isalnum() and (" " not in token)


# Allowed short words that count as meaningful for specific transformations
_ALLOWED_SHORT_WORDS = {"is", "no"}
_ALLOWED_NEGATION_PARSED = {"is", "no", "never"}
_ALLOWED_COMPARATOR_PARSED = {"less", "more", "lower", "higher", "greater", "fewer"}


def _is_meaningful_word(word: str) -> bool:
    # Heuristic: letters only and length >= 3, or allowed short words
    if not word:
        return False
    if word.lower() in _ALLOWED_SHORT_WORDS:
        return True
    return bool(re.fullmatch(r"[A-Za-z]{3,}", word or ""))


def _is_numeric_like(s: str) -> bool:
    return bool(re.fullmatch(r"[0-9]+(\.[0-9]+)?", s or ""))


def _validate_candidate_local(stem_text: str, visual: str, parsed: str, pos: Dict[str, Any]) -> None:
    cs = pos.get("char_start"); ce = pos.get("char_end")
    if not isinstance(cs, int) or not isinstance(ce, int) or cs < 0 or ce <= cs or ce > len(stem_text):
        raise RuntimeError("Invalid positions")
    if stem_text[cs:ce] != visual:
        raise RuntimeError("Slice mismatch with visual_entity")
    # Uniqueness in stem
    if stem_text.find(visual) != cs or stem_text.find(visual, cs + 1) != -1:
        raise RuntimeError("Visual entity not unique in stem")
    if not _is_single_alnum(visual):
        raise RuntimeError("Visual must be a single alphanumeric token")
    if visual == parsed:
        raise RuntimeError("Identity mapping not allowed")
    if len(visual) < len(parsed):
        raise RuntimeError("Require visual length >= parsed length")
    # Parsed must be meaningful word or numeric/comparator-type change
    if not (_is_meaningful_word(parsed) or _is_numeric_like(parsed)):
        raise RuntimeError("Parsed must be a meaningful word or numeric")


def _find_unique_single_alnum_tokens(stem_text: str, disallowed: list[str]) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    dis = {str(x).lower() for x in (disallowed or [])}
    try:
        for m in re.finditer(r"\b[A-Za-z0-9]+\b", stem_text or ""):
            t = m.group(0)
            if not t or (" " in t) or (not t.isalnum()):
                continue
            tl = t.lower()
            if tl in dis:
                continue
            # uniqueness check (case-sensitive exact)
            first = stem_text.find(t)
            second = stem_text.find(t, first + 1) if first != -1 else -1
            if first != -1 and second == -1:
                tokens.append({
                    "idx": len(tokens),
                    "text": t,
                    "char_start": m.start(),
                    "char_end": m.end(),
                })
    except Exception:
        pass
    return tokens


def _extract_negations(stem_text: str) -> list[dict[str, Any]]:
    negs = {"not", "never", "least", "except", "no", "none", "without"}
    out: list[dict[str, Any]] = []
    for m in re.finditer(r"\b([A-Za-z]+)\b", stem_text or ""):
        w = m.group(1)
        if w.lower() in negs:
            out.append({"text": w, "char_start": m.start(), "char_end": m.end()})
    return out


def _extract_numerics(stem_text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(r"\b\d+(?:\.\d+)?\b", stem_text or ""):
        out.append({"text": m.group(0), "char_start": m.start(), "char_end": m.end()})
    return out


def _true_false_value_to_label(options: Dict[str, str], value: str) -> str | None:
    want = (value or "").strip().lower()
    for lbl, txt in (options or {}).items():
        tv = (txt or "").strip().lower()
        if tv in {want, f"{want}.", f"{want}!", f"{want}?"}:
            return lbl
    return None


def _normalize_target_wrong(q_type: str, options: Dict[str, str], target_wrong: Any) -> Any:
    if q_type == "mcq_multi":
        if isinstance(target_wrong, list):
            cleaned: list[str] = []
            for x in target_wrong:
                s = str(x).strip().upper().rstrip(")").lstrip("(")
                if s in options and s not in cleaned:
                    cleaned.append(s)
            return cleaned or ([] if options else target_wrong)
        return [] if options else target_wrong
    if q_type == "mcq_single":
        s = str(target_wrong or "").strip().upper().rstrip(")").lstrip("(")
        if s in options:
            return s
        # try map by option text equality
        low = s.lower()
        for lbl, txt in options.items():
            if txt.strip().lower() == low:
                return lbl
        # try T/F mapping
        tf = _true_false_value_to_label(options, s)
        if tf:
            return tf
        # last resort
        return (next(iter(options.keys()), s) if options else s)
    if q_type == "true_false":
        s = str(target_wrong or "").strip().lower()
        return "True" if s.startswith("t") else "False"
    # others: text
    return target_wrong


def generate_structured_entities_v3(question: Dict[str, Any]) -> Dict[str, Any]:
    """V3: Return entities with strict positions and a meaningful parsed token.

    This function does not validate the flip; it only enforces local constraints. Flip validation is handled by llm_validation_service in a single call that can also propose alternatives.
    """
    q_type = (question.get("q_type") or "").strip()
    stem_text: str = question.get("stem_text") or ""
    options: Dict[str, str] = question.get("options") or {}
    correct_answer = question.get("correct_answer") or question.get("gold_answer") or None
    disallowed = extract_formatted_tokens(question, question.get("_ocr_doc")) if isinstance(question, dict) else []

    # Candidate inventories
    candidates = _find_unique_single_alnum_tokens(stem_text, disallowed)
    negations = _extract_negations(stem_text)
    numerics = _extract_numerics(stem_text)
    # Simple comparator lexicon for local checks
    comparator_lex = {"less", "more", "lower", "higher", "greater", "fewer", "least", "most"}

    repeated = _compute_repeated_tokens(stem_text)

    payload = {
        "q_type": q_type,
        "stem_text": stem_text,
        "options": options,
        "correct_answer": ({"label": str(correct_answer), "text": options.get(str(correct_answer), "")} if correct_answer else None),
        "disallowed_formatted_tokens": disallowed,
        "repeated_token_inventory": repeated,
        "candidate_tokens": candidates,
        "negation_tokens": negations,
        "numeric_tokens": numerics,
    }

    prompt = (
        "You will choose ONE token in the STEM and design a glyph-mapping edit that forces the parsed question to select a specific WRONG answer.\n"
        "Return STRICT JSON only. No prose.\n\n"
        "Rules:\n"
        "- Select the token by candidate_index from candidate_tokens (0-based).\n"
        "- entities.visual_entity MUST equal candidate_tokens[candidate_index].text exactly.\n"
        "- positions.char_start/char_end MUST equal candidate_tokens[candidate_index].char_start/char_end.\n"
        "- entities.parsed_entity MUST DIFFER from visual_entity and be a MEANINGFUL English word (letters-only, len>=3) OR a valid numeric/comparator change.\n"
        "- Enforce len(visual_entity) >= len(parsed_entity). If parsed would be longer, choose a longer candidate_index instead.\n"
        "- Prefer causally relevant tokens (negations, comparators, numbers tied to the solution, or key domain terms).\n"
        "- For MCQ/TF: also return target_wrong label(s) that the parsed question would select (must be among options if options exist).\n"
        "- For others: return a short target_wrong text (expected parsed answer).\n"
        "- If your edit is a NEGATION or COMPARATOR change, parsed_entity MUST be from these sets: negation={is,no,never}, comparator={less,more,lower,higher,greater,fewer}.\n"
        "\n"
        f"Question JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Output:\n"
        "{\n  \"entities\": {\"visual_entity\": \"...\", \"parsed_entity\": \"...\"},\n  \"positions\": {\"char_start\": 0, \"char_end\": 0},\n  \"candidate_index\": 0,\n  \"target_wrong\": <string or [string]>,\n  \"transformation\": \"numeric\"|\"negation\"|\"substitution\"|\"comparator\",\n  \"evidence_tokens\": [{\"text\":\"...\", \"role\":\"...\"}],\n  \"rationale\": \"<=20 words\"\n}"
    )

    logger.debug("[code_glyph_entity_service] V3 prompt: %s", prompt)
    content = _call_openai(prompt)
    logger.debug("[code_glyph_entity_service] Generation content for V3 step: %s", content)
    if not content:
        raise RuntimeError("LLM returned no content for v3")
    obj = _extract_json(content) or {}

    ents = obj.get("entities") or {}
    v = str(ents.get("visual_entity", ""))
    p = str(ents.get("parsed_entity", ""))
    pos = obj.get("positions") or {}
    # Normalize target_wrong immediately
    tw_raw = obj.get("target_wrong")
    tw = _normalize_target_wrong(q_type, options, tw_raw)

    # Snap/mend positions if needed using candidate_tokens
    def _snap_positions_by_visual(visual: str, current_pos: Dict[str, Any]) -> Dict[str, Any]:
        try:
            cs = int(current_pos.get("char_start")); ce = int(current_pos.get("char_end"))
        except Exception:
            cs = -1; ce = -1
        # If slice matches, keep
        if 0 <= cs < ce <= len(stem_text) and stem_text[cs:ce] == visual:
            return {"char_start": cs, "char_end": ce}
        # Else, find matching candidate by text
        matches = [c for c in candidates if c.get("text") == visual]
        if len(matches) == 1:
            return {"char_start": int(matches[0]["char_start"]), "char_end": int(matches[0]["char_end"])}
        # Else, unique search
        idx = stem_text.find(visual)
        if idx != -1 and stem_text.find(visual, idx + 1) == -1:
            return {"char_start": idx, "char_end": idx + len(visual)}
        # Give up (will fail validation later)
        return {"char_start": cs, "char_end": ce}

    pos = _snap_positions_by_visual(v, pos)

    # Enforce visual≥parsed (truncate parsed if necessary before deeper validation)
    if len(v) < len(p):
        # Try to re-host to a longer candidate first
        longer = next((c for c in candidates if len(str(c.get("text", ""))) >= len(p)), None)
        if longer:
            v = str(longer["text"])  # adopt longer host
            pos = {"char_start": int(longer["char_start"]), "char_end": int(longer["char_end"])}
        else:
            p = p[: len(v)]

    # If parsed not meaningful and this is MCQ/TF with a valid target_wrong, salvage from option text
    def _salvage_meaningful_from_option(option_label: str, max_len: int) -> str | None:
        if not option_label or option_label not in options:
            return None
        txt = options.get(option_label, "")
        # pick the first letters-only token with len>=3 and <= max_len
        for w in re.findall(r"[A-Za-z]{3,}", txt):
            if len(w) <= max_len:
                return w
        # fallback: letters-only root truncated to max_len
        m = re.search(r"[A-Za-z]{3,}", txt)
        if m:
            return m.group(0)[: max_len]
        return None

    # Enforce controlled sets for negation/comparator edits
    is_neg_visual = any((v.lower() == (n.get("text") or "").lower()) for n in negations)
    is_comp_visual = (v.lower() in comparator_lex)
    transf = str(obj.get("transformation") or "").lower()
    if transf in {"negation", "comparator"} or is_neg_visual or is_comp_visual:
        allowed = (_ALLOWED_NEGATION_PARSED if (transf == "negation" or is_neg_visual) else _ALLOWED_COMPARATOR_PARSED)
        # choose an allowed token that fits length
        if p.lower() not in allowed or len(p) > len(v):
            replacement = next((w for w in allowed if len(w) <= len(v)), None)
            if replacement:
                p = replacement

    if not (_is_meaningful_word(p) or _is_numeric_like(p)):
        if q_type in {"mcq_single", "mcq_multi", "true_false"} and tw:
            if isinstance(tw, list) and tw:
                salv = _salvage_meaningful_from_option(tw[0], len(v))
            else:
                salv = _salvage_meaningful_from_option(str(tw), len(v))
            if salv and salv != v:
                p = salv

    # Final local validation
    _validate_candidate_local(stem_text, v, p, pos)

    # Build backward-compatible anchor too
    cs = int(pos.get("char_start")); ce = int(pos.get("char_end"))
    anchor = {"char_start": cs, "char_end": ce, "anchor_text": stem_text[cs:ce]}

    result: Dict[str, Any] = {
        "entities": {"input_entity": v, "output_entity": p},
        "positions": pos,
        "anchor": anchor,
        "target_wrong": tw,
        "transformation": obj.get("transformation"),
        "evidence_tokens": obj.get("evidence_tokens") or [],
        "rationale": obj.get("rationale"),
    }

    logger.info("[code_glyph_entity_service] V3 entities: %s", {"entities": result["entities"], "target_wrong": result.get("target_wrong")})
    return result 


def _build_long_form_prompt(stem_text: str, candidate_spans: list[dict[str, int]]) -> str:
    joined = "\n".join(
        f"- token: '{stem_text[c['char_start']:c['char_end']]}' at [{c['char_start']},{c['char_end']})"
        for c in candidate_spans[:10]
    )
    return (
        "### Task\n"
        "Propose a substitution for a Code Glyph attack on a long-form question.\n\n"
        "### Rules\n"
        "- Return STRICT JSON only (no prose, no code fences).\n"
        "- Pick exactly ONE candidate token/span from the provided list as visual_entity.\n"
        "- output_entity may be MULTI-TOKEN and may include spaces, commas, and periods.\n"
        "- The substitution must MATERIALLY change the task intent/requirements (e.g., exactly→at most, at least→at most, must→may, include→exclude, before→after, maximum→minimum, all→any, 5→3).\n"
        "- Avoid trivial near-synonyms (e.g., list→choose, explain→describe).\n"
        "- Prefer spans whose replacement changes the required action (e.g., 'Define and explain'→'Differentiate').\n"
        "- Enforce len(output_entity) <= len(visual_entity).\n"
        "- Do NOT pick proper nouns unless they change domain (e.g., 'database'→'cloud').\n\n"
        "### Few‑shot Examples (good mappings)\n"
        "1. database → cloud\n"
        "2. Define and explain → Differentiate\n"
        "3. avoid → cause\n"
        "4. queries → joins\n\n"
        f"### Stem Text\n{stem_text}\n\n"
        f"### Candidate Spans (first 10)\n{joined or '(none)'}\n\n"
        "### Output (STRICT JSON)\n"
        "{\n"
        "  \"entities\": {\"input_entity\": \"<visual_entity>\", \"output_entity\": \"<parsed_entity>\"},\n"
        "  \"positions\": {\"char_start\": <int>, \"char_end\": <int>},\n"
        "  \"reason\": \"<<=120 chars>\"\n"
        "}"
    )


def cg_generate_structured_entities_v3(question: Dict[str, Any]) -> Dict[str, Any]:
    q_type = (question.get("q_type") or "").strip().lower()
    stem = question.get("stem_text") or ""
    if q_type in {"long_answer", "short_answer", "comprehension_qa", "fill_blank"}:
        # Build simple candidate spans (up to 10) by scanning tokens
        cands: list[dict[str, int]] = []
        for i in range(len(stem)):
            if stem[i].isspace():
                continue
            # extend to next space/punct
            j = i
            while j < len(stem) and not stem[j].isspace():
                j += 1
            if j - i >= 2:
                cands.append({"char_start": i, "char_end": j})
            if len(cands) >= 20:
                break
        # Restrict to tokens that appear exactly once in the stem (avoid ambiguous repeated words)
        stem_lower = stem.lower()
        unique_cands: list[dict[str, int]] = []
        for c in cands:
            token = stem_lower[c["char_start"]:c["char_end"]]
            # count non-overlapping occurrences
            occ = stem_lower.count(token)
            if occ == 1:
                unique_cands.append(c)
        cands = unique_cands or cands  # if none unique, keep original list to avoid empty
        prompt = build_long_form_prompt(stem, cands, extra_few_shots=None)
        logger.info("[code_glyph_entity_service] V3 prompt (first 400 chars): %s", prompt[:400])
        content = _call_openai(prompt)
        if content:
            logger.info("[code_glyph_entity_service] V3 content (first 400 chars): %s", content[:400])
        parsed = _extract_json(content or "") if content else None
        if isinstance(parsed, dict):
            ents = (parsed.get("entities") or {})
            pos = (parsed.get("positions") or {})
            vin = str(ents.get("input_entity", "")).strip()
            vout = str(ents.get("output_entity", "")).strip()
            cs = int(pos.get("char_start", -1))
            ce = int(pos.get("char_end", -1))
            # Enforce uniqueness of the chosen input_entity in the stem to avoid ambiguous mapping
            is_unique = False
            if vin:
                vin_lower = vin.lower()
                is_unique = (stem_lower.count(vin_lower) == 1)
            if vin and vout and 0 <= cs < ce <= len(stem) and len(vout) <= len(vin) and is_unique:
                return {
                    "entities": {"input_entity": vin, "output_entity": vout},
                    "positions": {"char_start": cs, "char_end": ce},
                    "target_wrong": None,
                    "transformation": "long_form_flip",
                }
        # Fallback minimal signal for renderer if generation fails
        return {
            "entities": {"input_entity": "and", "output_entity": "or"},
            "positions": {"char_start": 0, "char_end": 3},
            "target_wrong": None,
            "_fallback": True,
        }
    # All other types operate on stem_text
    ents = obj.get("entities") or {}
    v = str(ents.get("visual_entity", ""))
    p = str(ents.get("parsed_entity", ""))
    v, p = _enforce_lengths(v, p)

    # Enforce single-token alphanumeric and non-identity for non-match
    if (not v) or (v == p) or (" " in v) or (not v.isalnum()):
        raise RuntimeError("V2 invalid entity: require single alphanumeric visual token, non-identity, visual>=parsed")

    anchor = obj.get("anchor") or {}
    try:
        cs = int(anchor.get("char_start"))
        ce = int(anchor.get("char_end"))
    except Exception:
        cs = -1; ce = -1

    # Validate anchor against stem_text; if invalid, attempt to auto-correct by unique search
    if 0 <= cs < ce <= len(stem_text) and stem_text[cs:ce] == v:
        pass
    else:
        idx = _unique_idx(stem_text, v)
        if idx >= 0:
            cs, ce = idx, idx + len(v)
        else:
            # Hard failure: cannot anchor uniquely
            raise RuntimeError("V2 entity anchor validation failed")

    result = {
        "entities": {"input_entity": v, "output_entity": p},
        "anchor": {"char_start": cs, "char_end": ce, "anchor_text": stem_text[cs:ce]},
    }

    # target_wrong normalization
    if q_type == "mcq_multi":
        tw = obj.get("target_wrong") or []
        if isinstance(tw, list):
            result["target_wrong"] = [str(x).strip().upper().rstrip(")").lstrip("(") for x in tw]
    elif q_type == "mcq_single":
        tw = obj.get("target_wrong")
        if isinstance(tw, str):
            result["target_wrong"] = tw.strip().upper().rstrip(")").lstrip("(")
    elif q_type == "true_false":
        tw = obj.get("target_wrong")
        if isinstance(tw, str):
            val = tw.strip().lower()
            result["target_wrong"] = "True" if val.startswith("t") else "False"
    else:
        # fill/short/long/comprehension
        result["target_wrong"] = obj.get("target_wrong")

    # Carry through optional diagnostics
    for k in ("baseline_inference", "after_inference", "flip_validated", "transformation", "evidence_tokens"):
        if k in obj:
            result[k] = obj.get(k)

    logger.info("[code_glyph_entity_service] V2 entities: %s", {k: (v if k != "entities" else result["entities"]) for k, v in result.items() if k in {"entities", "target_wrong"}})
    return result 


def generate_code_glyph_v1_entities(stem_text: str, options: Dict[str, str]) -> Dict[str, str]:
    return generate_entities_for_question(stem_text, options)


def generate_code_glyph_v2_entities(question: Dict[str, Any]) -> Dict[str, Any]:
    return generate_structured_entities_v2(question)


def generate_code_glyph_v3_entities(questions: List[Dict[str, Any]], ocr_doc: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for q in questions or []:
        try:
            results.append(generate_structured_entities_v3(q))
        except Exception:
            results.append({})
    return results 