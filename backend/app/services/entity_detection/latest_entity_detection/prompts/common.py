from __future__ import annotations

import json
from typing import Any, Dict, List


HARD_RULES_HEADER = (
	"### Task\n"
	"Perform a SINGLE adversarial substitution on the academic question.\n\n"
	"### Hard Rules (Must Do)\n"
	"- Pick EXACTLY ONE contiguous substring from the Stem Text as visual_entity (no candidate list provided).\n"
	"- Return 0-based [char_start, char_end) indices that slice that exact substring.\n"
	"- len(output_entity) <= len(visual_entity); prefer strictly shorter.\n"
	"- output_entity may include spaces, commas, periods, hyphen; max 3 words.\n"
	"- Change must MATERIALLY alter requirements/domain/ordering/modality/comparator/quantity.\n"
	"- Use provided gold answer to choose a target_wrong that differs from gold.\n"
	"- Prefer characters reliably supported by our glyph mapping: ASCII letters/digits, space, comma, period, hyphen.\n"
	"- Output STRICT JSON only.\n\n"
	"### Hard Rules (Must NOT Do)\n"
	"- Do NOT modify more than one span.\n"
	"- Do NOT pick trivial near-synonyms or proper nouns (unless domain shift alters requirements).\n"
	"- Do NOT return anything other than the JSON object(s).\n\n"
)

SELECTION_HEURISTICS = (
	"### Selection Heuristics (Priority)\n"
	"A) Domain/object swaps (binary→linear, cost→loss, neural→Bayes)\n"
	"B) Quantities & comparatives (at least N→at most M, ≤→>)\n"
	"C) Capability flips (capable→unable)\n"
	"D) Temporal order (before↔after)\n"
	"E) Modality (must→may)\n"
	"F) Inequalities (≤↔≥; <↔>)\n\n"
)

FEW_SHOT_CATALOG = (
	"### Shorthand Few‑Shot Pairs\n"
	"1. binary → linear\n"
	"2. cost curve → loss curve\n"
	"3. neural → Bayes\n"
	"4. three → two\n"
	"5. at least three → at most two\n"
	"6. all → no\n"
	"7. capable → unable\n"
	"8. must → may\n"
	"9. before → after\n"
	"10. ≤ → >\n"
	"11. 5 → 4\n\n"
)

JSON_OUTPUT_NOTE = (
	"### Output (STRICT JSON)\n"
	"If returning multiple options, respond with a JSON array of objects.\n"
	"Each object must be: {\n"
	"  \"entities\": {\"input_entity\": \"<visual_entity>\", \"output_entity\": \"<parsed_entity>\"},\n"
	"  \"positions\": {\"char_start\": <int>, \"char_end\": <int>},\n"
	"  \"reason\": \"<=120 chars\",\n"
	"  \"target_wrong\": <type-specific>,\n"
	"  \"rationale_steps\": [\"step 1\", \"step 2\", ...]\n"
	"}\n"
)


def build_shared_preamble() -> str:
	return HARD_RULES_HEADER + SELECTION_HEURISTICS + FEW_SHOT_CATALOG


def to_json(obj: Any) -> str:
	return json.dumps(obj, ensure_ascii=False)


def build_input_block(stem_text: str, options: Dict[str, str] | None, matches: List[Dict[str, str]] | None, gold_answer: Any) -> str:
	parts: List[str] = [
		"### Inputs\n",
		f"Stem Text:\n{stem_text}\n\n",
		f"Gold Answer:\n{to_json(gold_answer)}\n\n",
	]
	if options:
		parts.append(f"Options:\n{to_json(options)}\n\n")
	if matches:
		parts.append(f"Matches:\n{to_json(matches)}\n\n")
	return "".join(parts)


def build_topk_suffix(top_k: int) -> str:
	return (
		"Return up to " + str(top_k) + " options, ordered by strongest expected flip first.\n\n" + JSON_OUTPUT_NOTE
	) 