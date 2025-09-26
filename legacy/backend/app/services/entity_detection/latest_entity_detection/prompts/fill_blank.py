from __future__ import annotations

from typing import Any

from .common import build_shared_preamble, build_input_block, build_topk_suffix


FILL_FEW_SHOTS = (
	"### Worked Few‑Shot Examples (fill_blank)\n"
	"Stem: 'Bias is __ to variance in the trade-off.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"to variance\", \"output_entity\": \"greater than\"}, \"positions\": {\"char_start\": 9, \"char_end\": 20}, \"reason\": \"Comparator insertion changes expected fill.\", \"target_wrong\": \"inversely\"}\n\n"
	"Stem: 'The gradient is computed __ normalization.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"computed\", \"output_entity\": \"omitted\"}, \"positions\": {\"char_start\": 13, \"char_end\": 21}, \"reason\": \"Verb change alters processing stage.\", \"target_wrong\": \"after\"}\n\n"
	"Stem: 'Regularization strength should be __ than 0.01.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"than 0.01\", \"output_entity\": \"at most\"}, \"positions\": {\"char_start\": 33, \"char_end\": 42}, \"reason\": \"Quantity reformulation changes bound.\", \"target_wrong\": \"greater\"}\n\n"
	"Stem: 'Validation loss must be __ training loss.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"must be\", \"output_entity\": \"may be\"}, \"positions\": {\"char_start\": 16, \"char_end\": 22}, \"reason\": \"Modality relaxes constraint; different fill.\", \"target_wrong\": \"lower than\"}\n\n"
)


def build_prompt(stem_text: str, gold_answer: Any, top_k: int) -> str:
	preamble = build_shared_preamble()
	inputs = build_input_block(stem_text, None, None, gold_answer)
	task = (
		"### Type: fill_blank\n"
		"Select one substring whose substitution changes the expected filled text.\n"
		"Return target_wrong as a short text (<=5 words) different from gold.\n\n"
	)
	return preamble + FILL_FEW_SHOTS + inputs + task + build_topk_suffix(top_k) 