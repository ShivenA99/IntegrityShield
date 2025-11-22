from __future__ import annotations

import json
import os
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

    def _resolve_openai_model(self, provider: str) -> str:
        configured = (
            current_app.config.get("POST_FUSER_MODEL")
            or os.getenv("POST_FUSER_MODEL")
            or current_app.config.get("OPENAI_DEFAULT_MODEL")
            or os.getenv("OPENAI_DEFAULT_MODEL")
        )
        suffix = ""
        if ":" in provider:
            suffix = provider.split(":", 1)[1].strip()
        elif provider == "openai":
            suffix = ""
        normalized = suffix.lower()
        if normalized not in {"", "auto", "fusion", "default"}:
            return suffix

        fallback = (configured or "gpt-4o").strip()
        if fallback.lower().startswith("gpt-5"):
            # Avoid GPT-5 default usage now that fusion is gated to OpenAI Vision output
            fallback = "gpt-4o"
        return fallback

    def _call_openai_chat(
        self,
        model: str,
        prompt: str,
        response_format: Optional[Dict[str, Any]] = None,
        generation_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        api_key = current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not configured")
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover
            self.logger.error("OpenAI SDK import failed: %s", exc)
            raise

        client = OpenAI(api_key=api_key)
        gen_opts: Dict[str, Any] = generation_options or {}
        request_args: Dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Return only the final answer (e.g., an option letter or short text).",
                },
                {"role": "user", "content": prompt},
            ],
        }
        for param in ("top_p", "presence_penalty", "frequency_penalty"):
            if param in gen_opts:
                request_args[param] = gen_opts[param]
        if response_format:
            request_args["response_format"] = response_format

        temperature = gen_opts.get("temperature")
        is_gpt5 = model.lower().startswith("gpt-5")
        if temperature is not None:
            if is_gpt5 and temperature not in (1, 1.0):
                self.logger.debug(
                    "Ignoring unsupported temperature %.3f for %s (using model default)",
                    temperature,
                    model,
                )
            elif not is_gpt5:
                request_args["temperature"] = temperature
        else:
            if not is_gpt5:
                request_args["temperature"] = 0.0

        token_limit = (
            gen_opts.get("max_completion_tokens")
            or gen_opts.get("max_output_tokens")
            or gen_opts.get("max_tokens")
        )
        if token_limit is not None:
            request_args["max_completion_tokens"] = token_limit
        else:
            request_args["max_completion_tokens"] = 200

        try:
            resp = client.chat.completions.create(**request_args)
            content = (resp.choices[0].message.content or "").strip()  # type: ignore[attr-defined]
            raw_payload = self._serialize_openai_response(resp)
            return self._build_result(model, prompt, content, raw_payload)
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
        if provider.startswith("openai"):
            model = self._resolve_openai_model(provider)
            response_format = payload.get("response_format")
            if not isinstance(response_format, dict):
                response_format = None
            generation_options = payload.get("generation_options")
            if not isinstance(generation_options, dict):
                generation_options = {}
            for key in (
                "temperature",
                "top_p",
                "presence_penalty",
                "frequency_penalty",
                "max_tokens",
                "max_completion_tokens",
                "max_output_tokens",
            ):
                if key in payload and key not in generation_options:
                    generation_options[key] = payload[key]

            result = self._call_openai_chat(
                model,
                prompt,
                response_format,
                generation_options=generation_options,
            )
            result["provider"] = f"openai:{model}"
            return result

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

    def _build_result(
        self,
        model: str,
        prompt: str,
        content: str,
        raw_payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "provider": f"openai:{model}",
            "prompt": prompt,
            "response": content.strip(),
            "confidence": 0.9,
        }
        if raw_payload is not None:
            result["raw_response"] = raw_payload
        return result

    def _serialize_openai_response(self, response: Any) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(response.model_dump_json())  # type: ignore[attr-defined]
        except Exception:
            try:
                return response.model_dump()  # type: ignore[attr-defined]
            except Exception:
                try:
                    return response.to_dict()  # type: ignore[attr-defined]
                except Exception:
                    return None
