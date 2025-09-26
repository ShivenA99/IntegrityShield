from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, List
import base64
import json
from pathlib import Path

logger = logging.getLogger(__name__)

try:
	from mistralai import Mistral  # type: ignore
except Exception:
	Mistral = None  # type: ignore


@dataclass
class MistralConfig:
	api_key: Optional[str] = os.getenv("MISTRAL_API_KEY")
	model: str = os.getenv("MISTRAL_MODEL", "pixtral-12b-2409")
	timeout_s: int = int(os.getenv("OCR_TIMEOUT_S", "120"))


class MistralClient:
	def __init__(self, cfg: Optional[MistralConfig] = None):
		self.cfg = cfg or MistralConfig()
		if not self.cfg.api_key:
			logger.warning("[NEW_OCR][MISTRAL] No MISTRAL_API_KEY set; skipping vendor OCR calls.")

	def _to_b64(self, png_b64: str | bytes) -> str:
		if isinstance(png_b64, bytes):
			return base64.b64encode(png_b64).decode("utf-8")
		return png_b64

	def _split_tokens_lines(self, text: str) -> tuple[list[str], list[Dict[str, Any]]]:
		lines = [ln for ln in (text.splitlines() if text else []) if ln.strip()]
		tokens: list[Dict[str, Any]] = []
		for ln in lines:
			for t in ln.split():
				tokens.append({"text": t})
		return lines, tokens

	def _complete_with_image(self, prompt: str, b64: str) -> str:
		client = Mistral(api_key=self.cfg.api_key)
		resp = client.chat.complete(
			model=self.cfg.model,
			messages=[
				{
					"role": "user",
					"content": [
						{"type": "text", "text": prompt},
						{"type": "image", "image_url": f"data:image/png;base64,{b64}"},
					],
				}
			],
		)
		return (resp.choices[0].message["content"] if hasattr(resp.choices[0], "message") else resp.choices[0]["message"]["content"]).strip()  # type: ignore

	def _extract_json_obj(self, text: str) -> Dict[str, Any] | None:
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

	def ocr_page(self, page_png_b64: str) -> Dict[str, Any]:
		"""Call Mistral vision/chat to get markdown. Returns {tokens, lines, markdown, confidence}."""
		if not (self.cfg.api_key and Mistral):
			return {"tokens": [], "lines": [], "markdown": "", "confidence": 0.0}
		try:
			prompt = (
				"Extract ALL visible text from this page as clean Markdown.\n"
				"- Preserve headings, lists, tables (use pipes), math (LaTeX inline $...$).\n"
				"- Keep ordering and line breaks.\n"
				"- Do NOT add explanations. Output Markdown only."
			)
			b64 = self._to_b64(page_png_b64)
			text = self._complete_with_image(prompt, b64)
			lines, tokens = self._split_tokens_lines(text or "")
			conf = 0.9 if text else 0.0
			logger.info("[NEW_OCR][MISTRAL] page markdown length=%d", len(text or ""))
			return {"tokens": tokens, "lines": lines, "markdown": text, "confidence": conf}
		except Exception as e:
			logger.warning("[NEW_OCR][MISTRAL] OCR failed: %s", e)
			return {"tokens": [], "lines": [], "markdown": "", "confidence": 0.0}

	def ocr_region_b64(self, crop_png_b64: str, *, task: str = "text") -> Dict[str, Any]:
		"""OCR a cropped region (base64 PNG). Returns standardized {markdown, lines, tokens, confidence}."""
		if not (self.cfg.api_key and Mistral):
			return {"tokens": [], "lines": [], "markdown": "", "confidence": 0.0}
		try:
			if task == "table":
				prompt = (
					"Transcribe this table region as Markdown using pipes. Include headers if present.\n"
					"Output table only; no explanations."
				)
			else:
				prompt = (
					"Transcribe this text region as clean Markdown, preserving punctuation and case.\n"
					"No explanations; output content only."
				)
			text = self._complete_with_image(prompt, self._to_b64(crop_png_b64))
			lines, tokens = self._split_tokens_lines(text or "")
			conf = 0.85 if text else 0.0
			return {"tokens": tokens, "lines": lines, "markdown": text, "confidence": conf}
		except Exception as e:
			logger.warning("[NEW_OCR][MISTRAL] region OCR failed: %s", e)
			return {"tokens": [], "lines": [], "markdown": "", "confidence": 0.0}

	def ocr_page_blocks(self, page_png_bytes_or_b64: bytes | str, blocks_px: List[Dict[str, Any]]) -> Dict[str, Any]:
		"""Single-call ROI OCR. blocks_px: [{"block_id": str, "bbox_px": [x0,y0,x1,y1]}].
		Returns {"blocks": [{"block_id": str, "markdown": str}], "confidence": float}.
		"""
		if not (self.cfg.api_key and Mistral):
			return {"blocks": [], "confidence": 0.0}
		try:
			b64 = self._to_b64(page_png_bytes_or_b64)
			# Include image size for context if bytes
			img_w = img_h = None
			try:
				if isinstance(page_png_bytes_or_b64, (bytes, bytearray)):
					from PIL import Image  # type: ignore
					import io as _io
					with Image.open(_io.BytesIO(page_png_bytes_or_b64)) as im:
						img_w, img_h = im.size
			except Exception:
				pass
			payload = {"image_px": {"width": img_w, "height": img_h}, "blocks": blocks_px}
			prompt = (
				"Transcribe text within the given rectangles, one JSON object per input block_id.\n"
				"STRICT JSON: {\"blocks\": [{\"block_id\": str, \"markdown\": str}, ...]}\n"
			)
			# Provide prompt and input JSON in separate content parts before the image
			client = Mistral(api_key=self.cfg.api_key)
			resp = client.chat.complete(
				model=self.cfg.model,
				messages=[
					{"role": "user", "content": [
						{"type": "text", "text": prompt},
						{"type": "text", "text": "INPUT_JSON:\n" + json.dumps(payload, ensure_ascii=False)},
						{"type": "image", "image_url": f"data:image/png;base64,{b64}"},
					]},
				],
			)
			text = (resp.choices[0].message["content"] if hasattr(resp.choices[0], "message") else resp.choices[0]["message"]["content"]).strip()  # type: ignore
			obj = self._extract_json_obj(text or "") or {}
			blocks = obj.get("blocks") if isinstance(obj, dict) else None
			logger.info("[NEW_OCR][MISTRAL] ROI requested_blocks=%d returned=%d", len(blocks_px or []), len(blocks or []))
			if isinstance(blocks, list):
				return {"blocks": blocks, "confidence": 0.85}
			return {"blocks": [], "confidence": 0.0}
		except Exception as e:
			logger.warning("[NEW_OCR][MISTRAL] ocr_page_blocks failed: %s", e)
			return {"blocks": [], "confidence": 0.0}

	def doc_ocr_pdf(self, pdf_path: Path, *, include_images: bool = False) -> Dict[str, Any]:
		"""Run Mistral document OCR/annotations on the entire PDF and return page-level markdown list.
		Returns {"pages": [{"page_index": int, "markdown": str}], "raw": <original_response>}.
		"""
		if not (self.cfg.api_key and Mistral):
			return {"pages": [], "raw": None}
		try:
			client = Mistral(api_key=self.cfg.api_key)
			# Build document chunk as data URL
			b64 = base64.b64encode(Path(pdf_path).read_bytes()).decode("utf-8")
			doc_chunk = {"type": "document_url", "document_url": f"data:application/pdf;base64,{b64}"}
			# Try annotations first
			try:
				resp = client.document_ai.annotate(
					document=doc_chunk,
					annotation_types=["bbox", "doc_annot"],
					include_images=include_images,
				)
				raw = resp.model_dump() if hasattr(resp, "model_dump") else json.loads(resp.model_dump_json())
			except Exception:
				raw = None
			# Fallback to OCR process endpoint
			if not raw:
				resp = client.ocr.process(
					model="mistral-ocr-2505",
					document=doc_chunk,
					include_image_base64=include_images,
				)
				raw = resp.model_dump() if hasattr(resp, "model_dump") else json.loads(resp.model_dump_json())
			# Extract page markdowns if available
			pages_out: List[Dict[str, Any]] = []
			for i, pg in enumerate(raw.get("pages", []) or []):
				md = (pg.get("markdown") or pg.get("text") or "").strip()
				pages_out.append({"page_index": i, "markdown": md})
			logger.info("[NEW_OCR][MISTRAL][DOC] pages=%d", len(pages_out))
			return {"pages": pages_out, "raw": raw}
		except Exception as e:
			logger.warning("[NEW_OCR][MISTRAL][DOC] OCR failed: %s", e)
			return {"pages": [], "raw": None} 