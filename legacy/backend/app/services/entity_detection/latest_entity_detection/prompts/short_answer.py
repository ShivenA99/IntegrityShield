from __future__ import annotations

from typing import Any

from .common import build_shared_preamble, build_input_block, build_topk_suffix


SHORT_FEW_SHOTS = (
	"### Worked Few‑Shot Examples (short_answer)\n"
	"Stem: 'Explain the role of the learning rate.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"Explain\", \"output_entity\": \"Justify\"}, \"positions\": {\"char_start\": 0, \"char_end\": 7}, \"reason\": \"Shifts task from description to defense.\", \"target_wrong\": \"choose schedule\"}\n\n"
	"Stem: 'Define cross-validation in one sentence.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"Define\", \"output_entity\": \"Differentiate\"}, \"positions\": {\"char_start\": 0, \"char_end\": 6}, \"reason\": \"Definition→comparison alters expected answer.\", \"target_wrong\": \"contrast folds\"}\n\n"
	"Stem: 'Describe the purpose of a confusion matrix.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"Describe\", \"output_entity\": \"Summarize\"}, \"positions\": {\"char_start\": 0, \"char_end\": 8}, \"reason\": \"Task reframing changes response scope.\", \"target_wrong\": \"list entries\"}\n\n"
	"Stem: 'List two advantages of regularization.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"two\", \"output_entity\": \"one\"}, \"positions\": {\"char_start\": 5, \"char_end\": 8}, \"reason\": \"Quantity change reduces obligation.\", \"target_wrong\": \"improves speed\"}\n\n"
)


def build_prompt(stem_text: str, gold_answer: Any, top_k: int) -> str:
	preamble = build_shared_preamble()
	inputs = build_input_block(stem_text, None, None, gold_answer)
	task = (
		"### Type: short_answer\n"
		"Select one substring whose substitution changes the expected concise response.\n"
		"Return target_wrong as a short text (<=5 words) different from gold.\n\n"
	)
	return preamble + SHORT_FEW_SHOTS + inputs + task + build_topk_suffix(top_k) 