from __future__ import annotations

from typing import Any, Dict, List

from .common import build_shared_preamble, build_input_block, build_topk_suffix


MATCH_FEW_SHOTS = (
	"### Worked Few‑Shot Examples (match)\n"
	"Stem: 'Match each algorithm to its primary objective.'\n"
	"Matches: [{\"L\":\"A\",\"R\":\"1\"},{\"L\":\"B\",\"R\":\"2\"},{\"L\":\"C\",\"R\":\"3\"}]\n"
	"GOOD → {\"entities\": {\"input_entity\": \"primary objective\", \"output_entity\": \"training dataset\"}, \"positions\": {\"char_start\": 28, \"char_end\": 45}, \"reason\": \"Relation basis change alters pairing.\", \"target_wrong\": [{\"L\":\"A\",\"R\":\"3\"},{\"L\":\"B\",\"R\":\"1\"},{\"L\":\"C\",\"R\":\"2\"}]}\n\n"
	"Stem: 'Match each metric to its definition.'\n"
	"Matches: [{\"L\":\"P\",\"R\":\"i\"},{\"L\":\"Q\",\"R\":\"ii\"}]\n"
	"GOOD → {\"entities\": {\"input_entity\": \"definition\", \"output_entity\": \"example\"}, \"positions\": {\"char_start\": 20, \"char_end\": 30}, \"reason\": \"Definition→example shifts mapping.\", \"target_wrong\": [{\"L\":\"P\",\"R\":\"ii\"},{\"L\":\"Q\",\"R\":\"i\"}]}\n\n"
	"Stem: 'Match the researcher to the method they proposed.'\n"
	"Matches: [{\"L\":\"1\",\"R\":\"A\"},{\"L\":\"2\",\"R\":\"B\"},{\"L\":\"3\",\"R\":\"C\"}]\n"
	"GOOD → {\"entities\": {\"input_entity\": \"proposed\", \"output_entity\": \"rejected\"}, \"positions\": {\"char_start\": 32, \"char_end\": 40}, \"reason\": \"Verb polarity inversion changes links.\", \"target_wrong\": [{\"L\":\"1\",\"R\":\"C\"},{\"L\":\"2\",\"R\":\"A\"},{\"L\":\"3\",\"R\":\"B\"}]}\n\n"
	"Stem: 'Match each theorem to the field it belongs to.'\n"
	"Matches: [{\"L\":\"α\",\"R\":\"I\"},{\"L\":\"β\",\"R\":\"II\"}]\n"
	"GOOD → {\"entities\": {\"input_entity\": \"belongs\", \"output_entity\": \"opposes\"}, \"positions\": {\"char_start\": 26, \"char_end\": 33}, \"reason\": \"Relation inversion alters destination field.\", \"target_wrong\": [{\"L\":\"α\",\"R\":\"II\"},{\"L\":\"β\",\"R\":\"I\"}]}\n\n"
)


def build_prompt(stem_text: str, matches: List[Dict[str, str]], gold_answer: Any, top_k: int) -> str:
	preamble = build_shared_preamble()
	inputs = build_input_block(stem_text, None, matches, gold_answer)
	task = (
		"### Type: match\n"
		"Select one substring whose substitution leads to a different valid mapping from left to right.\n"
		"Return target_wrong as a list of {L,R} pairs that deviates materially from the gold mapping.\n\n"
	)
	return preamble + MATCH_FEW_SHOTS + inputs + task + build_topk_suffix(top_k) 