from __future__ import annotations

from typing import List, Dict, Any

PROVIDED_FEW_SHOTS: List[tuple[str, str]] = [
    ("database", "cloud"),
    ("Define and explain", "Differentiate"),
    ("avoid", "cause"),
    ("queries", "joins"),
]


def build_candidate_list(stem_text: str, candidate_spans: List[Dict[str, int]]) -> str:
    lines: List[str] = []
    for c in candidate_spans[:10]:
        cs = int(c.get("char_start", -1)); ce = int(c.get("char_end", -1))
        if 0 <= cs < ce <= len(stem_text):
            token = stem_text[cs:ce]
            lines.append(f"- token: '{token}' at [{cs},{ce})")
    return "\n".join(lines) or "(none)"


def build_long_form_prompt(stem_text: str, candidate_spans: List[Dict[str, int]], extra_few_shots: List[tuple[str, str]] | None = None) -> str:
    candidates_md = build_candidate_list(stem_text, candidate_spans)
    few_shots = list(PROVIDED_FEW_SHOTS)
    if extra_few_shots:
        few_shots.extend(extra_few_shots)
    few_shots_md = "\n".join([f"{i+1}. {src} → {tgt}" for i, (src, tgt) in enumerate(few_shots)])

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
        f"{few_shots_md}\n\n"
        f"### Stem Text\n{stem_text}\n\n"
        f"### Candidate Spans (first 10)\n{candidates_md}\n\n"
        "### Output (STRICT JSON)\n"
        "{\n"
        "  \"entities\": {\"input_entity\": \"<visual_entity>\", \"output_entity\": \"<parsed_entity>\"},\n"
        "  \"positions\": {\"char_start\": <int>, \"char_end\": <int>},\n"
        "  \"reason\": \"<<=120 chars>\"\n"
        "}"
    )


def build_structured_v2_prompt(question: Dict[str, Any]) -> str:
    import json as _json
    q_type = (question.get("q_type") or "").strip()
    stem_text: str = question.get("stem_text") or ""
    options: Dict[str, str] = question.get("options") or {}
    correct_answer = question.get("correct_answer") or question.get("gold_answer") or None
    matches = question.get("matches") or []
    # external helpers would compute disallowed/repeated; keep simple in prompt context
    payload = {
        "q_type": q_type,
        "stem_text": stem_text,
        "options": options,
        "correct_answer": ({"label": str(correct_answer), "text": options.get(str(correct_answer), "")} if correct_answer else None),
        "match_pairs": ([{"L": m.get("left", ""), "R": m.get("right", "")}] if q_type == "match" else None),
    }
    return (
        "You will design a single glyph-mapping edit that forces the PARSED question to select a specific WRONG answer.\n"
        "Follow SOLVE→EDIT→SIMULATE and return STRICT JSON only. No prose, no code fences.\n\n"
        "Global constraints:\n"
        "- Operate only on STEM (except q_type='match' where you operate on options).\n"
        "- entities.visual_entity MUST be an exact, case-sensitive substring that occurs exactly once.\n"
        "- Provide anchor.char_start and anchor.char_end (exclusive) and anchor.anchor_text (must equal the slice).\n"
        "- visual_entity length >= parsed_entity length.\n"
        "- visual_entity MUST be a SINGLE ALPHANUMERIC TOKEN (no spaces, no punctuation).\n"
        "- parsed_entity MUST DIFFER from visual_entity (no identity mappings).\n"
        "- Prefer numbers and negation/comparator edits, but ONLY if they are relevant to the answer.\n"
        "- After the edit (parsed question), the selected answer MUST equal target_wrong.\n\n"
        f"Question JSON:\n{_json.dumps(payload, ensure_ascii=False)}\n\n"
        "Type-specific rules:\n"
        "- mcq_single/mcq_multi: choose target_wrong from options; edit STEM only.\n"
        "- true_false: flip truth via negation/comparator/number; set target_wrong accordingly.\n"
        "- match: operate on options; minimally alter one side to induce a wrong mapping; return target_wrong_mapping.\n"
        "- others: edit STEM so the expected answer changes; set target_wrong to the new expected short answer.\n\n"
        "Output schema (by q_type):\n"
        "mcq_single/mcq_multi/true_false/others: {\"entities\":{\"visual_entity\":\"...\",\"parsed_entity\":\"...\"},\"anchor\":{\"char_start\":0,\"char_end\":0,\"anchor_text\":\"...\"},\"target_wrong\":<string or [string]>,\"baseline_inference\":{\"label\":<string|null>,\"text\":<string>},\"after_inference\":{\"label\":<string|null>,\"text\":<string>},\"flip_validated\":true}\n"
        "match: {\"entities\":[{\"visual_entity\":\"...\",\"parsed_entity\":\"...\",\"side\":\"L|R\",\"pair_index\":0,\"anchor\":{...}}],\"target_wrong_mapping\":[{\"L\":\"...\",\"R\":\"...\"}],\"flip_validated\":true}\n"
    ) 