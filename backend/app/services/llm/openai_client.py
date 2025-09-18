from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..evaluation.openai_eval_service import OPENAI_API_KEY

logger = logging.getLogger(__name__)


class OpenAIClient:
	def __init__(self):
		if not OPENAI_API_KEY:
			raise RuntimeError("OPENAI_API_KEY not configured")
		from openai import OpenAI  # type: ignore
		self._client = OpenAI(api_key=OPENAI_API_KEY)

	def upload_file(self, path: Path, purpose: str = "assistants") -> str:
		with open(path, "rb") as f:
			obj = self._client.files.create(file=f, purpose=purpose)
		return obj.id

	def responses(self, model: str, input: List[Dict[str, Any]]) -> Dict[str, Any]:
		resp = self._client.responses.create(model=model, input=input)
		return resp

	def chat_completions(self, model: str, messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
		resp = self._client.chat.completions.create(model=model, messages=messages, **kwargs)
		return resp 