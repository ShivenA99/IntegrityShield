from __future__ import annotations

from typing import Any, Dict

from .common import build_shared_preamble, build_input_block, build_topk_suffix


TF_FEW_SHOTS = (
	"### Worked Few‑Shot Examples (true_false)\n"
	"Stem: 'Gradients after normalization are stable.'\n"
	"Options: {A: 'True', B: 'False'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"after\", \"output_entity\": \"before\"}, \"positions\": {\"char_start\": 10, \"char_end\": 15}, \"reason\": \"Temporal swap flips truth condition.\", \"target_wrong\": \"False\"}\n\n"
	"Stem: 'All models with dropout generalize better.'\n"
	"Options: {A: 'True', B: 'False'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"All\", \"output_entity\": \"No\"}, \"positions\": {\"char_start\": 0, \"char_end\": 3}, \"reason\": \"Quantifier flip reverses claim.\", \"target_wrong\": \"False\"}\n\n"
	"Stem: 'A learning rate ≤ 0.1 guarantees convergence.'\n"
	"Options: {A: 'True', B: 'False'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"≤\", \"output_entity\": \"\u003e\"}, \"positions\": {\"char_start\": 16, \"char_end\": 17}, \"reason\": \"Inequality reversal changes statement.\", \"target_wrong\": \"False\"}\n\n"
	"Stem: 'Batch norm reduces internal covariate shift.'\n"
	"Options: {A: 'True', B: 'False'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"reduces\", \"output_entity\": \"raises\"}, \"positions\": {\"char_start\": 11, \"char_end\": 18}, \"reason\": \"Polarity flip reverses assertion.\", \"target_wrong\": \"False\"}\n\n"
)


def build_prompt(stem_text: str, options: Dict[str, str], gold_answer: Any, top_k: int) -> str:
	preamble = build_shared_preamble()
	inputs = build_input_block(stem_text, options, None, gold_answer)
	task = (
		"### Type: true_false\n"
		"Select one substring whose substitution flips the truth condition.\n"
		"Return target_wrong as exactly 'True' or 'False', opposite to the gold when known.\n\n"
	)
	return preamble + TF_FEW_SHOTS + inputs + task + build_topk_suffix(top_k) 