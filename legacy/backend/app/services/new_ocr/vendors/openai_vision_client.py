from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, Optional, List
import json

logger = logging.getLogger(__name__)

try:
	import openai  # type: ignore
except Exception:
	openai = None  # type: ignore


class OpenAIVisionClient:
	def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
		self.api_key = api_key or os.getenv("OPENAI_API_KEY")
		self.model = (model or os.getenv("OPENAI_VISION_MODEL", "gpt-4o")).strip()
		if not self.api_key:
			logger.warning("[NEW_OCR][OAI_VISION] OPENAI_API_KEY missing; hard-region augmentation disabled.")

	def _to_b64(self, png_bytes: bytes) -> str:
		return base64.b64encode(png_bytes).decode("utf-8")

	def _mk_client(self):
		if not (self.api_key and openai):
			return None, False
		try:
			if hasattr(openai, 'OpenAI'):
				return openai.OpenAI(api_key=self.api_key), True
			# Legacy SDK path; set global api_key if available
			try:
				setattr(openai, 'api_key', self.api_key)
			except Exception:
				pass
			return openai, False
		except Exception:
			return None, False

	def _split_tokens_lines(self, text: str) -> tuple[list[str], list[Dict[str, Any]]]:
		lines = [ln for ln in (text.splitlines() if text else []) if ln.strip()]
		tokens: list[Dict[str, Any]] = []
		for ln in lines:
			for t in ln.split():
				tokens.append({"text": t})
		return lines, tokens

	def _extract_json_obj(self, text: str) -> Dict[str, Any] | None:
		if not text:
			return None
		s = text.strip()
		# strip fences
		if s.startswith("```json") or s.startswith("```"):
			try:
				first_nl = s.find("\n")
				if first_nl != -1:
					s = s[first_nl + 1 :]
				if s.endswith("```"):
					s = s[:-3]
			except Exception:
				pass
		# try direct
		try:
			return json.loads(s)
		except Exception:
			pass
		# find first {...}
		try:
			start = s.find("{")
			end = s.rfind("}")
			if start != -1 and end != -1 and end > start:
				return json.loads(s[start:end+1])
		except Exception:
			return None
		return None

	def ocr_page_markdown(self, page_png_bytes: bytes) -> Dict[str, Any]:
		"""Return markdown and exact tokens/lines using OpenAI Vision."""
		if not (self.api_key and openai):
			return {"tokens": [], "lines": [], "markdown": "", "confidence": 0.0}
		try:
			client, is_new = self._mk_client()
			b64 = self._to_b64(page_png_bytes)
			prompt = (
				"Extract ALL visible text from this page as clean Markdown.\n"
				"- Preserve headings, lists, tables (use pipes), math (as LaTeX inline $...$).\n"
				"- Keep original ordering and line breaks.\n"
				"- Do NOT add explanations or metadata. Output Markdown only."
			)
			messages = [
				{"role": "user", "content": [
					{"type": "text", "text": prompt},
					{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
				]},
			]
			if is_new:
				resp = client.chat.completions.create(
					model=self.model,
					messages=messages,
					max_completion_tokens=4000,
					temperature=0.0,
				)
				text = (resp.choices[0].message.content or "").strip()
			else:
				resp = client.ChatCompletion.create(  # type: ignore
					model=self.model,
					messages=messages,
					max_tokens=4000,
					temperature=0.0,
				)
				text = (resp["choices"][0]["message"]["content"] if isinstance(resp, dict) else resp.choices[0].message.content or "").strip()
			lines, tokens = self._split_tokens_lines(text or "")
			conf = 0.9 if text else 0.0
			logger.info("[NEW_OCR][OAI_VISION] page markdown length=%d", len(text or ""))
			return {"tokens": tokens, "lines": lines, "markdown": text, "confidence": conf}
		except Exception as e:
			logger.warning("[NEW_OCR][OAI_VISION] Vision OCR failed: %s", e)
			return {"tokens": [], "lines": [], "markdown": "", "confidence": 0.0}

	def ocr_page_blocks(self, page_png_bytes: bytes, blocks_px: List[Dict[str, Any]]) -> Dict[str, Any]:
		"""Single-call ROI OCR. blocks_px: [{"block_id": str, "bbox_px": [x0,y0,x1,y1]}].
		Returns {"blocks": [{"block_id": str, "markdown": str}], "confidence": float}.
		"""
		if not (self.api_key and openai):
			return {"blocks": [], "confidence": 0.0}
		client, is_new = self._mk_client()
		b64 = self._to_b64(page_png_bytes)
		# Infer image size in pixels for context
		try:
			from PIL import Image  # type: ignore
			import io as _io
			with Image.open(_io.BytesIO(page_png_bytes)) as im:
				img_w, img_h = im.size
		except Exception:
			img_w = img_h = None
		payload = {"image_px": {"width": img_w, "height": img_h}, "blocks": blocks_px}
		prompt = (
			"Given a page image and a list of block rectangles in PIXEL coords (bbox_px),\n"
			"transcribe ONLY the text inside each rectangle as clean Markdown.\n"
			"Rules:\n"
			"- Output EXACTLY one entry per input block_id.\n"
			"- Preserve punctuation, case, math (LaTeX inline $...$), simple tables (pipes).\n"
			"- Do NOT include text outside the bbox.\n"
			"- STRICT JSON ONLY: {\"blocks\": [{\"block_id\": str, \"markdown\": str}, ...]}\n"
		)
		messages = [
			{"role": "user", "content": [
				{"type": "text", "text": prompt + "\nINPUT_JSON:\n" + json.dumps(payload, ensure_ascii=False)},
				{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
			]},
		]
		try:
			if is_new:
				resp = client.chat.completions.create(
					model=self.model,
					messages=messages,
					max_completion_tokens=6000,
					temperature=0.0,
				)
				text = (resp.choices[0].message.content or "").strip()
			else:
				resp = client.ChatCompletion.create(  # type: ignore
					model=self.model,
					messages=messages,
					max_tokens=6000,
					temperature=0.0,
				)
				text = (resp["choices"][0]["message"]["content"] if isinstance(resp, dict) else resp.choices[0].message.content or "").strip()
			obj = self._extract_json_obj(text or "") or {}
			blocks = obj.get("blocks") if isinstance(obj, dict) else None
			logger.info("[NEW_OCR][OAI_VISION] ROI requested_blocks=%d returned=%d", len(blocks_px or []), len(blocks or []))
			if isinstance(blocks, list):
				return {"blocks": blocks, "confidence": 0.9}
			return {"blocks": [], "confidence": 0.0}
		except Exception as e:
			logger.warning("[NEW_OCR][OAI_VISION] ocr_page_blocks failed: %s", e)
			return {"blocks": [], "confidence": 0.0}

	def annotate_region(self, crop_png_b64: str, task: str) -> Dict[str, Any]:
		if not (self.api_key and openai):
			return {"ok": False, "reason": "no_api_key"}
		logger.info("[NEW_OCR][OAI_VISION] annotate_region task=%s", task)
		try:
			client, is_new = self._mk_client()
			prompt = (
				"You will transcribe a small region from a document.\n"
				"Task type: " + str(task) + "\n"
				"- For text: return the exact text as Markdown (preserve punctuation and case).\n"
				"- For table: return a Markdown table using pipes and headers if present.\n"
				"- Do NOT add explanations. Output content only."
			)
			img_url = f"data:image/png;base64,{crop_png_b64}"
			if is_new:
				resp = client.chat.completions.create(
					model=self.model,
					messages=[{"role": "user", "content": [
						{"type": "text", "text": prompt},
						{"type": "image_url", "image_url": {"url": img_url}},
					]}],
					max_completion_tokens=1500,
					temperature=0.0,
				)
				text = (resp.choices[0].message.content or "").strip()
			else:
				resp = client.ChatCompletion.create(  # type: ignore
					model=self.model,
					messages=[{"role": "user", "content": [
						{"type": "text", "text": prompt},
						{"type": "image_url", "image_url": {"url": img_url}},
					]}],
					max_tokens=1500,
					temperature=0.0,
				)
				text = (resp["choices"][0]["message"]["content"] if isinstance(resp, dict) else resp.choices[0].message.content or "").strip()
			lines, tokens = self._split_tokens_lines(text or "")
			conf = 0.85 if text else 0.0
			return {"ok": True, "task": task, "markdown": text, "lines": lines, "tokens": tokens, "confidence": conf}
		except Exception as e:
			logger.warning("[NEW_OCR][OAI_VISION] annotate_region failed: %s", e)
			return {"ok": False, "reason": str(e)}

	def latex_from_region(self, crop_png_b64: str) -> Dict[str, Any]:
		if not (self.api_key and openai):
			return {"ok": False, "reason": "no_api_key"}
		logger.info("[NEW_OCR][OAI_VISION] latex_from_region called.")
		try:
			client, is_new = self._mk_client()
			prompt = (
				"Extract ONLY the mathematical content from this region as LaTeX.\n"
				"- Use inline $...$ or display $$...$$ as appropriate.\n"
				"- If no math, return plain text.\n"
				"- Do NOT add any explanations."
			)
			img_url = f"data:image/png;base64,{crop_png_b64}"
			if is_new:
				resp = client.chat.completions.create(
					model=self.model,
					messages=[{"role": "user", "content": [
						{"type": "text", "text": prompt},
						{"type": "image_url", "image_url": {"url": img_url}},
					]}],
					max_completion_tokens=1000,
					temperature=0.0,
				)
				text = (resp.choices[0].message.content or "").strip()
			else:
				resp = client.ChatCompletion.create(  # type: ignore
					model=self.model,
					messages=[{"role": "user", "content": [
						{"type": "text", "text": prompt},
						{"type": "image_url", "image_url": {"url": img_url}},
					]}],
					max_tokens=1000,
					temperature=0.0,
				)
				text = (resp["choices"][0]["message"]["content"] if isinstance(resp, dict) else resp.choices[0].message.content or "").strip()
			latex = text if ("$" in (text or "") or "\\(" in (text or "") or "\\[" in (text or "")) else ""
			plain = text if not latex else ""
			conf = 0.85 if text else 0.0
			return {"ok": True, "latex": latex, "text": plain, "confidence": conf}
		except Exception as e:
			logger.warning("[NEW_OCR][OAI_VISION] latex_from_region failed: %s", e)
			return {"ok": False, "reason": str(e)} 