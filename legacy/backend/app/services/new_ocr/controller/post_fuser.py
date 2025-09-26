from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
	import openai  # type: ignore
	_HAS_NEW = hasattr(openai, 'OpenAI')
except Exception:
	openai = None  # type: ignore
	_HAS_NEW = False


def _mk_client():
	api_key = os.getenv("OPENAI_API_KEY")
	if not (api_key and openai):
		return None, False
	try:
		if _HAS_NEW:
			return openai.OpenAI(api_key=api_key), True
		try:
			setattr(openai, 'api_key', api_key)
		except Exception:
			pass
		return openai, False
	except Exception:
		return None, False


def _extract_json_obj(text: str) -> Dict[str, Any] | None:
	if not text:
		return None
	s = text.strip()
	if s.startswith("```json") or s.startswith("```"):
		try:
			first_nl = s.find("\n")
			if first_nl != -1:
				s = s[first_nl + 1 :]
			if s.endswith("```"):
				s = s[:-3]
		except Exception:
			pass
	try:
		return json.loads(s)
	except Exception:
		pass
	try:
		start = s.find("{")
		end = s.rfind("}")
		if start != -1 and end != -1 and end > start:
			return json.loads(s[start:end+1])
	except Exception:
		return None
	return None


def _build_prompt(ast_pages: List[Dict[str, Any]], vendor_pages: Dict[str, List[Dict[str, Any]]]) -> str:
	"""Construct a strict instruction prompt for GPT-5 post-fusion of questions & anchors.
	We pass a compacted view: per page, list of text_block items with {id, markdown/text, index_map}.
	"""
	def compact_page(p: Dict[str, Any]) -> Dict[str, Any]:
		items = []
		for it in p.get("items", []) or []:
			if it.get("type") == "text_block":
				items.append({
					"id": it.get("id"),
					"text": it.get("text", ""),
					"markdown": it.get("markdown", it.get("text", "")),
					"index_map": it.get("index_map", []),
				})
		return {"page_index": p.get("page_index"), "items": items}

	compact = [compact_page(p) for p in ast_pages or []]
	bundle = {
		"pages": compact,
		"vendor": {
			"openai": vendor_pages.get("openai", []),
			"mistral": vendor_pages.get("mistral", []),
		},
	}
	contract = (
		"You are a strict post-fuser. Given an immutable PDF layout spine (pages->text_block ids with markdown/index_map)\n"
		"and two OCR vendors' text, extract questions in STRICT JSON that references ONLY existing block ids.\n\n"
		"Rules:\n"
		"- Do NOT add, modify, or reorder pages or block ids.\n"
		"- For each question, you MUST set: q_number, q_type, stem_text, options (empty object for non-MCQ), context_ids (array of existing text_block ids).\n"
		"- You MAY optionally include anchors = [{block_id, char_start, char_end}] over the chosen block markdown. If uncertain, omit anchors but KEEP the question.\n"
		"- Classify q_type as one of: mcq_single|mcq_multi|true_false|match|fill_blank|short_answer|long_answer|comprehension_qa.\n"
		"- Preserve numbering including sub-questions (e.g., '1', '1a', '2').\n"
		"- Output STRICT JSON ONLY with keys: {\"title\": str, \"questions\": [...]}. No fences, no prose.\n\n"
	)
	return contract + "INPUT:\n" + json.dumps(bundle, ensure_ascii=False)


def post_fuse_questions(ast_doc: Dict[str, Any], vendor_openai_pages: List[Dict[str, Any]], vendor_mistral_pages: List[Dict[str, Any]]) -> Dict[str, Any]:
	"""Call OpenAI to produce title and questions using the AST as the spine.
	Returns {title: str, questions: [...]}. On failure, returns {}.
	"""
	client, is_new = _mk_client()
	if not client:
		logger.warning("[NEW_OCR][POST_FUSER] No OpenAI client available; skipping post-fusion.")
		return {}
	try:
		ast_pages = (ast_doc.get("document", {}) or {}).get("pages", [])
		prompt = _build_prompt(ast_pages, {"openai": vendor_openai_pages, "mistral": vendor_mistral_pages})
		logger.info("[NEW_OCR][POST_FUSER] Calling GPT post-fuser (prompt size=%d)", len(prompt))
		if is_new:
			resp = client.chat.completions.create(
				model=os.getenv("POST_FUSER_MODEL", "gpt-5"),
				messages=[{"role": "user", "content": prompt}],
				max_completion_tokens=4000,
			)
			text = (resp.choices[0].message.content or "").strip()
		else:
			resp = client.ChatCompletion.create(  # type: ignore
				model=os.getenv("POST_FUSER_MODEL", "gpt-5"),
				messages=[{"role": "user", "content": prompt}],
				max_tokens=4000,
			)
			text = (resp["choices"][0]["message"]["content"] if isinstance(resp, dict) else resp.choices[0].message.content or "").strip()
		obj = _extract_json_obj(text) or {}
		title = obj.get("title")
		questions = obj.get("questions") or []
		if isinstance(questions, list):
			return {"title": title, "questions": questions}
		return {}
	except Exception as e:
		logger.warning("[NEW_OCR][POST_FUSER] Fusion call failed: %s", e)
		return {} 