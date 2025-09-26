from __future__ import annotations

from typing import Any

from .common import build_shared_preamble, build_input_block, build_topk_suffix


LONG_FORM_FEW_SHOTS = (
	"### Worked Few‑Shot Examples (validated)\n"
	"Stem: 'Define and explain the working of a binary search algorithm in detail.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"binary\", \"output_entity\": \"linear\"}, \"positions\": {\"char_start\": 36, \"char_end\": 42}, \"reason\": \"Domain swap changes algorithm type and complexity.\"}\n\n"
	"Stem: 'Using the provided data, students must construct a cost curve and then evaluate market efficiency.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"cost curve\", \"output_entity\": \"loss curve\"}, \"positions\": {\"char_start\": 51, \"char_end\": 61}, \"reason\": \"Changes object of analysis; alters required derivations.\"}\n\n"
	"Stem: 'Students must include references to at least three peer-reviewed articles.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"at least three\", \"output_entity\": \"at most two\"}, \"positions\": {\"char_start\": 36, \"char_end\": 50}, \"reason\": \"Reduces obligation; changes grading rubric.\"}\n\n"
	"Stem: 'Before modeling, discuss the data preprocessing pipeline in detail.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"Before\", \"output_entity\": \"After\"}, \"positions\": {\"char_start\": 0, \"char_end\": 6}, \"reason\": \"Temporal flip changes narrative and requirements.\"}\n\n"
)


def build_prompt(stem_text: str, gold_answer: Any, top_k: int) -> str:
	preamble = build_shared_preamble()
	inputs = build_input_block(stem_text, None, None, gold_answer)
	task = (
		"### Type: long_answer\n"
		"Select one substring whose substitution materially changes the task requirements or evaluation burden.\n"
		"Return target_wrong as a short text (<=5 words) different from gold.\n\n"
	)
	return preamble + LONG_FORM_FEW_SHOTS + inputs + task + build_topk_suffix(top_k) 