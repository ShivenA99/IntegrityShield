from __future__ import annotations

from typing import Any, Dict

from .common import build_shared_preamble, build_input_block, build_topk_suffix


MCQ_SINGLE_FEW_SHOTS = (
	"### Worked Few‑Shot Examples (mcq_single)\n"
	"Stem: 'Choose the algorithm for binary classification.'\n"
	"Options: {A: 'Linear regression', B: 'Naive Bayes', C: 'SVM (linear)', D: 'Logistic regression'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"binary\", \"output_entity\": \"linear\"}, \"positions\": {\"char_start\": 25, \"char_end\": 31}, \"reason\": \"Domain swap changes algorithm family; flips choice.\", \"target_wrong\": \"B\"}\n\n"
	"Stem: 'Students must cite at least three sources.'\n"
	"Options: {A: 'Cite two sources', B: 'Cite three sources', C: 'Cite any one source', D: 'No citations'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"at least three\", \"output_entity\": \"at most two\"}, \"positions\": {\"char_start\": 19, \"char_end\": 33}, \"reason\": \"Quantity bound reduction changes correct option.\", \"target_wrong\": \"A\"}\n\n"
	"Stem: 'Before evaluation, select the metric to optimize.'\n"
	"Options: {A: 'Validation accuracy', B: 'F1 before training', C: 'AUC after deployment', D: 'Pre‑training loss'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"Before\", \"output_entity\": \"After\"}, \"positions\": {\"char_start\": 0, \"char_end\": 6}, \"reason\": \"Temporal flip alters which metric applies first.\", \"target_wrong\": \"C\"}\n\n"
	"Stem: 'The report must include proofs.'\n"
	"Options: {A: 'Provide optional sketches', B: 'Include proofs', C: 'Only give results', D: 'Add code appendix'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"must\", \"output_entity\": \"may\"}, \"positions\": {\"char_start\": 11, \"char_end\": 15}, \"reason\": \"Modality relaxation changes obligation.\", \"target_wrong\": \"A\"}\n\n"
)


def build_prompt(stem_text: str, options: Dict[str, str], gold_answer: Any, top_k: int) -> str:
	preamble = build_shared_preamble()
	inputs = build_input_block(stem_text, options, None, gold_answer)
	task = (
		"### Type: mcq_single\n"
		"Select one substring that, when replaced, causes the parsed question to prefer a different option label than the gold.\n"
		"Return target_wrong as a single label in Options and not equal to the gold label.\n\n"
	)
	return preamble + MCQ_SINGLE_FEW_SHOTS + inputs + task + build_topk_suffix(top_k) 