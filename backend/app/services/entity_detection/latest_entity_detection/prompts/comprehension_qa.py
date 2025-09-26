from __future__ import annotations

from typing import Any

from .common import build_shared_preamble, build_input_block, build_topk_suffix


COMP_FEW_SHOTS = (
	"### Worked Few‑Shot Examples (comprehension_qa)\n"
	"Stem: 'Based on the passage, explain how the optimizer adapts to curvature.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"explain\", \"output_entity\": \"justify\"}, \"positions\": {\"char_start\": 22, \"char_end\": 29}, \"reason\": \"Changes evaluation burden and focus.\", \"target_wrong\": \"Compare methods\"}\n\n"
	"Stem: 'According to the text, describe why early stopping improves generalization.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"describe why\", \"output_entity\": \"argue against\"}, \"positions\": {\"char_start\": 22, \"char_end\": 34}, \"reason\": \"Polarity change reverses stance.\", \"target_wrong\": \"harms generalization\"}\n\n"
	"Stem: 'From the article, list the steps before deployment.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"before\", \"output_entity\": \"after\"}, \"positions\": {\"char_start\": 33, \"char_end\": 39}, \"reason\": \"Temporal flip changes sequence expectations.\", \"target_wrong\": \"post-deploy steps\"}\n\n"
	"Stem: 'As stated, models with ≤ 5 layers converge faster.'\n"
	"GOOD → {\"entities\": {\"input_entity\": \"≤\", \"output_entity\": \"\u003e\"}, \"positions\": {\"char_start\": 20, \"char_end\": 21}, \"reason\": \"Inequality reversal changes claim focus.\", \"target_wrong\": \"slower convergence\"}\n\n"
)


def build_prompt(stem_text: str, gold_answer: Any, top_k: int) -> str:
	preamble = build_shared_preamble()
	inputs = build_input_block(stem_text, None, None, gold_answer)
	task = (
		"### Type: comprehension_qa\n"
		"Select one substring whose substitution shifts the expected answer to a different concise text.\n"
		"Return target_wrong as a short text (<=5 words) different from gold.\n\n"
	)
	return preamble + COMP_FEW_SHOTS + inputs + task + build_topk_suffix(top_k) 