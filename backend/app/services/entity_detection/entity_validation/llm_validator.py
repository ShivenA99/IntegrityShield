from __future__ import annotations

import json
import logging
import os
import unicodedata
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

try:
	from openai import OpenAI  # type: ignore
except Exception:
	OpenAI = None  # type: ignore

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("VALIDATOR_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
# Rule: require strictly shorter or allow equal length when flipping operators/quantifiers
ALLOW_EQUAL_LENGTH = os.getenv("CG_ALLOW_EQUAL_LENGTH", "0") in {"1", "true", "True"}
# Confidence threshold for non-MCQ/TF comparisons
DIFF_CONF_THRESH = float(os.getenv("CG_DIFF_CONF_THRESH", "0.6"))


def _normalize(s: str) -> str:
	# NFKC, collapse spaces, unify quotes/dashes
	n = unicodedata.normalize("NFKC", s or "")
	n = n.replace("\u00A0", " ")
	n = n.replace("–", "-").replace("—", "-")
	n = n.replace("“", '"').replace("”", '"').replace("’", "'")
	# collapse whitespace
	return " ".join(n.split())


def _normalize_label(label: str) -> str:
	return (_normalize(label) or "").strip().upper()


def _normalize_label_list(labels: List[str]) -> List[str]:
	return sorted([_normalize_label(l) for l in (labels or []) if isinstance(l, str) and l])


def _call_openai_json(prompt: str) -> str | None:
	if not OPENAI_API_KEY or not OpenAI:
		logger.warning("[LATEST_ENTITY][VALIDATE] OpenAI not configured; returning None")
		return None
	try:
		client = OpenAI(api_key=OPENAI_API_KEY)
		resp = client.chat.completions.create(
			model=OPENAI_MODEL,
			messages=[
				{"role": "system", "content": "You are a careful grader. Output STRICT JSON only."},
				{"role": "user", "content": prompt},
			],
			temperature=0.0,
			max_tokens=500,
		)
		content: str | None = resp.choices[0].message.content if resp and resp.choices else None
		if content:
			logger.info("[LATEST_ENTITY][VALIDATE] Content (first 400): %s", str(content)[:400])
		return content.strip() if content else None
	except Exception as e:
		logger.error("[LATEST_ENTITY][VALIDATE] OpenAI call failed: %s", e)
		return None


def _deterministic_checks(question: Dict[str, Any], option: Dict[str, Any]) -> Dict[str, Any]:
	stem_raw = question.get("stem_text") or ""
	ents = option.get("entities") or {}
	vin = ents.get("input_entity") or ""
	vout = ents.get("output_entity") or ""
	# Only enforce length policy deterministically; indices/slice are not required
	vin_norm = _normalize(str(vin))
	vout_norm = _normalize(str(vout))
	length_ok = False
	if len(vout_norm) <= len(vin_norm):
		length_ok = True
	elif ALLOW_EQUAL_LENGTH and len(vout_norm) == len(vin_norm):
		length_ok = True
	return {
		"length_ok": length_ok,
		"vin_len": len(vin_norm),
		"vout_len": len(vout_norm),
	}


def _resolve_span(text: str, entity_text: str) -> Tuple[int, int] | None:
	try:
		if not text or not entity_text:
			return None
		idx = text.find(entity_text)
		if idx == -1:
			idx = text.lower().find(entity_text.lower())
			if idx == -1:
				return None
		return (idx, idx + len(entity_text))
	except Exception:
		return None


def _build_edited_stem(stem_text: str, input_entity: str, output_entity: str) -> Tuple[str, Tuple[int, int] | None]:
	pos = _resolve_span(stem_text, input_entity)
	if not pos:
		return stem_text, None
	cs, ce = pos
	return stem_text[:cs] + output_entity + stem_text[ce:], (cs, ce)


def _build_answer_diff_prompt(q: Dict[str, Any], edited_stem: str, gold_answer: Any) -> str:
	qtype = (q.get("q_type") or "").strip()
	opts = q.get("options") or {}
	matches = q.get("matches") or []
	blanks = q.get("blanks") or []
	payload = {
		"q_type": qtype,
		"edited_stem": edited_stem,
		"gold_answer": gold_answer,
		"options": opts,
		"matches": matches,
		"blanks": blanks,
	}
	instructions = (
		"Answer the edited_stem, then compare your answer to gold_answer. Output STRICT JSON only.\n\n"
		"Rules per q_type:\n"
		"- mcq_single: edited_answer is a single label like 'A'.\n"
		"- mcq_multi: edited_answer is an array of labels like ['A','C'] (uppercase).\n"
		"- true_false: edited_answer is 'True' or 'False'.\n"
		"- fill_blank: edited_answer is just the filled text.\n"
		"- short_answer/long_answer: edited_answer <= 300 chars.\n\n"
		"Return JSON with keys: {\n"
		"  'edited_answer': <string|array|label>,\n"
		"  'differs': <bool>,\n"
		"  'confidence': <float 0.0-1.0>,\n"
		"  'reason': '<<=160 chars why differs or not>>',\n"
		"  'verdict': 'pass'|'fail'  // pass if differs, else fail\n"
		"}\n"
	)
	return "Context:\n" + json.dumps(payload, ensure_ascii=False) + "\n\n" + instructions


# ===================== PUBLIC ENTRY POINT =====================

def validate_entities_latest(question: Dict[str, Any], option: Dict[str, Any]) -> Dict[str, Any]:
	# Deterministic length policy only
	checks = _deterministic_checks(question, option)
	if not checks.get("length_ok"):
		note = f"output length {checks['vout_len']} > input length {checks['vin_len']}"
		return {"ok": False, "verdict": "length_violation", "notes": note, "used_rationale": False}

	stem = question.get("stem_text") or ""
	ents = option.get("entities") or {}
	vin = ents.get("input_entity") or ""
	vout = ents.get("output_entity") or ""

	# Build edited stem; if input entity not found, reject deterministically
	edited_stem, span = _build_edited_stem(stem, str(vin), str(vout))
	if span is None:
		return {"ok": False, "verdict": "reject_policy_violation", "notes": "input_entity not found as contiguous substring", "used_rationale": False}

	# Build and call LLM once to answer edited stem and compare vs gold
	gold = question.get("gold_answer") or question.get("correct_answer") or ""
	prompt = _build_answer_diff_prompt(question, edited_stem, gold)
	logger.info("[LATEST_ENTITY][VALIDATE] Prompt (first 400): %s", prompt[:400])
	content = _call_openai_json(prompt)
	if not content:
		return {"ok": False, "verdict": "no_content", "notes": "no llm response", "used_rationale": False}

	try:
		obj = json.loads(content)
	except Exception:
		return {"ok": False, "verdict": "parse_error", "notes": "invalid json", "used_rationale": False}

	qtype = (question.get("q_type") or "").strip()
	edited_answer = obj.get("edited_answer")
	differs = bool(obj.get("differs"))
	try:
		confidence = float(obj.get("confidence", 0.0))
	except Exception:
		confidence = 0.0
	reason = str(obj.get("reason", ""))[:160]
	# LLM-provided verdict is advisory; compute ok deterministically

	def _normalize_answer(val: Any) -> Any:
		if qtype == "mcq_single":
			return _normalize_label(str(val))
		if qtype == "mcq_multi":
			if isinstance(val, list):
				return _normalize_label_list(val)
			return _normalize_label_list([str(val)])
		if qtype == "true_false":
			v = str(val).strip().lower()
			return "True" if v.startswith("t") else "False"
		# fill/short/long/comprehension
		return _normalize(str(val))

	def _normalize_for_compare(val: Any) -> Any:
		if qtype in {"mcq_single", "mcq_multi", "true_false"}:
			return _normalize_answer(val)
		if qtype == "match":
			# Canonicalize as JSON for robust comparison
			try:
				if isinstance(val, dict):
					canon = {str(k).strip(): _normalize(str(v)) for k, v in val.items()}
					return json.dumps(canon, sort_keys=True, ensure_ascii=False)
				if isinstance(val, list):
					canon_list = [_normalize(str(x)) for x in val]
					return json.dumps(sorted(canon_list), ensure_ascii=False)
			except Exception:
				pass
			return _normalize(str(val))

	norm_gold = _normalize_answer(gold)
	norm_edited = _normalize_answer(edited_answer)

	# Prefer target_wrong comparator for specific q_types when provided
	target_wrong_raw = option.get("target_wrong") or question.get("wrong_label") or question.get("wrong_answer")
	use_target_cmp = qtype in {"mcq_single", "mcq_multi", "true_false", "match"} and target_wrong_raw is not None and target_wrong_raw != ""

	ok: bool
	if use_target_cmp:
		norm_tgt = _normalize_for_compare(target_wrong_raw)
		norm_edit_cmp = _normalize_for_compare(edited_answer)
		ok = norm_edit_cmp == norm_tgt
	elif qtype in {"mcq_single", "mcq_multi", "true_false"}:
		ok = norm_edited != norm_gold
	else:
		ok = bool(differs) and (confidence >= DIFF_CONF_THRESH)

	verdict = "pass" if ok else "fail"

	# Package response; include resolved span positions
	resp: Dict[str, Any] = {
		"ok": ok,
		"verdict": verdict,
		"notes": reason,
		"used_rationale": bool(option.get("rationale_steps") is not None),
		"confidence": confidence,
		"edited_answer": norm_edited if qtype != "mcq_multi" else norm_edited,  # already normalized
	}
	if span:
		cs, ce = span
		resp["resolved_positions"] = {"char_start": cs, "char_end": ce}
	return resp 