from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from flask import current_app

from ...utils.logging import get_logger


class ExternalAIClient:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.session = httpx.Client(timeout=30.0)

    def is_configured(self) -> bool:
        return bool(
            current_app.config.get("OPENAI_API_KEY")
            or current_app.config.get("ANTHROPIC_API_KEY")
            or current_app.config.get("GOOGLE_AI_KEY")
        )

    def _call_openai_chat(self, model: str, prompt: str) -> Dict[str, Any]:
        api_key = current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover
            self.logger.error("OpenAI SDK import failed: %s", exc)
            raise

        client = OpenAI(api_key=api_key)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant. Return only the final answer (e.g., an option letter or short text).",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=200,
            )
            content = (resp.choices[0].message.content or "").strip()  # type: ignore[attr-defined]
            return {
                "provider": f"openai:{model}",
                "prompt": prompt,
                "response": content,
                "confidence": 0.9,
            }
        except Exception as exc:
            self.logger.error("OpenAI chat call failed: %s", exc, exc_info=True)
            raise

    def call_model(self, provider: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_configured():
            self.logger.info("No AI provider configured; returning simulated response")
            return {
                "provider": provider,
                "prompt": payload.get("prompt"),
                "response": "simulated-response",
                "confidence": 0.5,
            }

        prompt: str = str(payload.get("prompt", "")).strip()
        if provider.startswith("openai:"):
            model = provider.split(":", 1)[1] or "gpt-4o-mini"
            return self._call_openai_chat(model, prompt)

        # Fallback simulated for other providers (extend as needed)
        self.logger.info("Unknown provider '%s'; returning simulated response", provider)
        return {
            "provider": provider,
            "prompt": prompt,
            "response": "simulated-response",
            "confidence": 0.5,
        }

    def close(self) -> None:
        self.session.close()
