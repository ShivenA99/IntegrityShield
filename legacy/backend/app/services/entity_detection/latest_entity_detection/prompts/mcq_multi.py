from __future__ import annotations

from typing import Any, Dict

from .common import build_shared_preamble, build_input_block, build_topk_suffix


MCQ_MULTI_FEW_SHOTS = (
	"### Worked Few‑Shot Examples (mcq_multi)\n"
	"Stem: 'Select all valid losses for binary classification.'\n"
	"Options: {A: 'Cross‑entropy', B: 'Hinge loss', C: 'MSE', D: 'CTC'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"binary\", \"output_entity\": \"multiclass\"}, \"positions\": {\"char_start\": 28, \"char_end\": 34}, \"reason\": \"Label‑space shift changes valid loss set.\", \"target_wrong\": [\"C\",\"D\"]}\n\n"
	"Stem: 'Choose all prerequisites with at least three steps.'\n"
	"Options: {A: 'Initialize config', B: 'Unit tests', C: 'Security review', D: 'Docs'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"at least three\", \"output_entity\": \"at most two\"}, \"positions\": {\"char_start\": 30, \"char_end\": 44}, \"reason\": \"Bound reduction alters which items qualify.\", \"target_wrong\": [\"B\",\"D\"]}\n\n"
	"Stem: 'Pipelines must include normalization and augmentation; select all applicable stages.'\n"
	"Options: {A: 'Normalization', B: 'Augmentation', C: 'Regularization', D: 'Tokenization'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"must\", \"output_entity\": \"may\"}, \"positions\": {\"char_start\": 10, \"char_end\": 14}, \"reason\": \"Modality change expands acceptable set.\", \"target_wrong\": [\"C\",\"D\"]}\n\n"
	"Stem: 'Enable these checks before deployment; select all that apply.'\n"
	"Options: {A: 'Rate limiting', B: 'Static analysis', C: 'Structured logging', D: 'Canary rollout'}\n"
	"GOOD → {\"entities\": {\"input_entity\": \"before\", \"output_entity\": \"after\"}, \"positions\": {\"char_start\": 20, \"char_end\": 26}, \"reason\": \"Temporal flip changes required controls.\", \"target_wrong\": [\"C\",\"D\"]}\n\n"
)


def build_prompt(stem_text: str, options: Dict[str, str], gold_answer: Any, top_k: int) -> str:
	preamble = build_shared_preamble()
	inputs = build_input_block(stem_text, options, None, gold_answer)
	task = (
		"### Type: mcq_multi\n"
		"Select one substring that, when replaced, shifts the correct set of labels.\n"
		"Return target_wrong as an array of labels from Options, differing from the gold set.\n\n"
	)
	return preamble + MCQ_MULTI_FEW_SHOTS + inputs + task + build_topk_suffix(top_k) 