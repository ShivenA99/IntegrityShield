from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
	from openai import OpenAI  # type: ignore
except Exception:
	OpenAI = None  # type: ignore

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Prefer a dedicated reasoning-capable model if provided; fallback to general model
OPENAI_MODEL = (
	os.getenv("LATEST_ENTITIES_MODEL")
	or os.getenv("OPENAI_REASONING_MODEL")
	or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
)


def _call_openai_json(prompt: str) -> str | None:
	if not OPENAI_API_KEY or not OpenAI:
		logger.warning("[LATEST_ENTITY] OpenAI not configured; returning None")
		return None
	try:
		client = OpenAI(api_key=OPENAI_API_KEY)
		resp = client.chat.completions.create(
			model=OPENAI_MODEL,
			messages=[
				{"role": "system", "content": "You are a careful assistant. Output STRICT JSON only."},
				{"role": "user", "content": prompt},
			],
			temperature=0.2,
			max_tokens=700,
		)
		content: str | None = resp.choices[0].message.content if resp and resp.choices else None
		if content:
			logger.info("[LATEST_ENTITY] OpenAI content (first 400): %s", str(content)[:400])
		return content.strip() if content else None
	except Exception as e:
		logger.error("[LATEST_ENTITY] OpenAI call failed: %s", e)
		return None


def _ensure_array(payload: Any) -> List[Any]:
	if isinstance(payload, list):
		return payload
	if isinstance(payload, dict):
		return [payload]
	return []


def _parse_json(content: str | None) -> List[Dict[str, Any]]:
	if not content:
		return []
	text = content.strip()
	# Tolerate single object or array
	try:
		parsed = json.loads(text)
		return _ensure_array(parsed)
	except Exception:
		# try to locate first JSON array or object
		start = text.find("[")
		alt_start = text.find("{")
		if start != -1 and (alt_start == -1 or start < alt_start):
			end = text.rfind("]")
			if end != -1:
				try:
					return _ensure_array(json.loads(text[start:end+1]))
				except Exception:
					return []
		if alt_start != -1:
			end = text.rfind("}")
			if end != -1:
				try:
					return _ensure_array(json.loads(text[alt_start:end+1]))
				except Exception:
					return []
		return []


def _build_prompt_for_question(q: Dict[str, Any], top_k: int) -> str:
	q_type = (q.get("q_type") or "").strip().lower()
	stem = q.get("stem_text") or ""
	options = q.get("options") or {}
	matches = q.get("matches") or []
	gold = q.get("gold_answer") or q.get("gold_answer_full") or ""
	from .prompts import mcq_single, mcq_multi, true_false, match, fill_blank, short_answer, long_answer, comprehension_qa
	if q_type == "mcq_single":
		return mcq_single.build_prompt(stem, options, gold, top_k)
	if q_type == "mcq_multi":
		return mcq_multi.build_prompt(stem, options, gold, top_k)
	if q_type == "true_false":
		return true_false.build_prompt(stem, options, gold, top_k)
	if q_type == "match":
		return match.build_prompt(stem, matches, gold, top_k)
	if q_type == "fill_blank":
		return fill_blank.build_prompt(stem, gold, top_k)
	if q_type == "short_answer":
		return short_answer.build_prompt(stem, gold, top_k)
	if q_type == "long_answer":
		return long_answer.build_prompt(stem, gold, top_k)
	if q_type == "comprehension_qa":
		pass
	# default: treat as short_answer
	return short_answer.build_prompt(stem, gold, top_k)


def generate_topk_entities_latest(question: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
	prompt = _build_prompt_for_question(question, top_k)
	logger.info("[LATEST_ENTITY] Prompt (first 400): %s", prompt[:400])
	content = _call_openai_json(prompt)
	options = _parse_json(content)
	# We assume options already include: entities, positions, reason, target_wrong, rationale_steps
	# Limit to top_k just in case
	return options[: top_k] if options else [] 