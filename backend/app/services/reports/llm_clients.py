from __future__ import annotations

import asyncio
import json
import ssl
import time
from pathlib import Path
from typing import Optional
import uuid

import aiohttp

from ...utils.logging import get_logger

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover - fallback when certifi unavailable
    SSL_CONTEXT = ssl.create_default_context()

logger = get_logger(__name__)


class LLMClientError(Exception):
    """Raised when a provider call fails."""


class BaseLLMClient:
    name: str

    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key or ""
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def upload_file(self, pdf_path: str) -> Optional[str]:
        raise NotImplementedError

    async def query_with_file(
        self,
        file_id: str | None,
        prompt: str,
        question_data: Optional[dict] = None,
    ) -> str:
        raise NotImplementedError


class OpenAIClient(BaseLLMClient):
    name = "openai"

    def __init__(self, api_key: str | None, model: str) -> None:
        super().__init__(api_key, model)
        self.base_url = "https://api.openai.com/v1"

    async def upload_file(self, pdf_path: str) -> str:
        # OpenAI combines upload + query; we return the original path
        if not Path(pdf_path).exists():
            raise LLMClientError(f"PDF not found at {pdf_path}")
        return pdf_path

    async def query_with_file(
        self,
        file_id: str | None,
        prompt: str,
        question_data: Optional[dict] = None,
    ) -> str:
        if not self.api_key:
            raise LLMClientError("OpenAI API key missing")

        pdf_path = file_id or ""
        if not pdf_path:
            raise LLMClientError("OpenAI requires the original pdf path reference")

        upload_url = f"{self.base_url}/files"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)

        async with aiohttp.ClientSession(connector=connector) as session:
            with open(pdf_path, "rb") as handle:
                data = aiohttp.FormData()
                data.add_field("file", handle, filename=Path(pdf_path).name, content_type="application/pdf")
                data.add_field("purpose", "user_data")
                async with session.post(upload_url, headers=headers, data=data) as resp:
                    if resp.status != 200:
                        raise LLMClientError(f"OpenAI upload failed: {await resp.text()}")
                    payload = await resp.json()
                    actual_file_id = payload["id"]

            file_status_url = f"{self.base_url}/files/{actual_file_id}"
            start = time.time()
            while time.time() - start < 90:
                async with session.get(file_status_url, headers=headers) as status_resp:
                    if status_resp.status == 200:
                        file_state = await status_resp.json()
                        if file_state.get("status") == "processed":
                            break
                        if file_state.get("status") == "error":
                            raise LLMClientError(f"OpenAI file processing failed: {file_state}")
                await asyncio.sleep(2)
            else:
                raise LLMClientError("OpenAI file processing timeout")

            final_prompt = prompt

            completion_payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You answer assessment questions using the attached PDF and respond ONLY with JSON.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "file", "file": {"file_id": actual_file_id}},
                            {"type": "text", "text": final_prompt},
                        ],
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 800,
            }

            async with session.post(
                f"{self.base_url}/chat/completions",
                headers={**headers, "Content-Type": "application/json"},
                data=json.dumps(completion_payload),
                timeout=aiohttp.ClientTimeout(total=180),
            ) as completion_resp:
                if completion_resp.status != 200:
                    raise LLMClientError(f"OpenAI completion failed: {await completion_resp.text()}")
                result = await completion_resp.json()
                choices = result.get("choices") or []
                if not choices:
                    raise LLMClientError("OpenAI returned no choices")
                return choices[0]["message"]["content"].strip()


class AnthropicClient(BaseLLMClient):
    name = "anthropic"

    def __init__(self, api_key: str | None, model: str, fallback_model: str | None = None) -> None:
        super().__init__(api_key, model)
        self.base_url = "https://api.anthropic.com/v1"
        self.file_id: Optional[str] = None
        self.fallback_model = fallback_model if fallback_model and fallback_model != model else None

    async def upload_file(self, pdf_path: str) -> Optional[str]:
        if not self.api_key:
            raise LLMClientError("Anthropic API key missing")

        url = f"{self.base_url}/files"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "files-api-2025-04-14",
        }
        data = aiohttp.FormData()
        with open(pdf_path, "rb") as handle:
            file_bytes = handle.read()
        data.add_field("file", file_bytes, filename=Path(pdf_path).name, content_type="application/pdf")

        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status != 200:
                    raise LLMClientError(f"Anthropic upload failed: {await resp.text()}")
                payload = await resp.json()
                self.file_id = payload.get("id")
                if not self.file_id:
                    raise LLMClientError("Anthropic did not return file id")
                return self.file_id

    async def query_with_file(
        self,
        file_id: str | None,
        prompt: str,
        question_data: Optional[dict] = None,
    ) -> str:
        if not self.api_key:
            raise LLMClientError("Anthropic API key missing")
        if not file_id:
            raise LLMClientError("Anthropic requires a file id")

        full_prompt = prompt

        # Anthropic API: text block should come before document block (original order)
        payload = {
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": full_prompt},
                        {"type": "document", "source": {"type": "file", "file_id": file_id}},
                    ],
                }
            ],
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "files-api-2025-04-14",
            "content-type": "application/json",
        }

        models_to_try = [self.model]
        if self.fallback_model and self.fallback_model not in models_to_try:
            models_to_try.append(self.fallback_model)

        last_error: Optional[Exception] = None
        for model_name in models_to_try:
            payload["model"] = model_name
            try:
                return await self._dispatch_completion(payload, headers)
            except LLMClientError as exc:
                last_error = exc
                error_text = str(exc)
                if (
                    model_name != self.fallback_model
                    and self.fallback_model
                    and "not_found_error" in error_text
                    and "model" in error_text
                ):
                    logger.warning(
                        "Anthropic model '%s' unavailable, retrying with fallback '%s'.",
                        model_name,
                        self.fallback_model,
                    )
                    continue
                raise

        if last_error:
            raise last_error
        raise LLMClientError("Anthropic completion failed without a clear error.")

    async def _dispatch_completion(self, payload: dict[str, object], headers: dict[str, str]) -> str:
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(
                        "Anthropic API error: status=%d, body=%s, payload=%s",
                        resp.status,
                        body[:500],
                        json.dumps(payload, indent=2)[:500],
                    )
                    raise LLMClientError(self._format_anthropic_error(body, resp.status))
                result = await resp.json()
                content = result.get("content") or []
                if not content:
                    raise LLMClientError("Anthropic returned empty content")
                first = content[0]
                if isinstance(first, dict) and "text" in first:
                    response_text = first["text"]
                    if payload.get("model"):
                        self.model = payload["model"]  # type: ignore[assignment]
                    logger.debug("Anthropic response (first 500 chars): %s", response_text[:500])
                    return response_text
                logger.warning("Anthropic returned unexpected content format: %s", first)
                return str(first)

    @staticmethod
    def _format_anthropic_error(body: str, status: int) -> str:
        try:
            parsed = json.loads(body)
            error = parsed.get("error") or {}
            message = error.get("message") or parsed.get("message") or body
            code = error.get("type") or parsed.get("type") or "unknown_error"
            return f"Anthropic completion failed ({status}, {code}): {message}"
        except Exception:
            return f"Anthropic completion failed ({status}): {body}"


class GoogleClient(BaseLLMClient):
    name = "google"

    def __init__(self, api_key: str | None, model: str) -> None:
        super().__init__(api_key, model)
        # Use v1beta API for file uploads support (file_data requires v1beta)
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def upload_file(self, pdf_path: str) -> Optional[str]:
        if not self.api_key:
            raise LLMClientError("Google API key missing")

        upload_base = "https://generativelanguage.googleapis.com/upload/v1beta"
        url = f"{upload_base}/files?uploadType=multipart&key={self.api_key}"
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        with open(pdf_path, "rb") as handle:
            file_bytes = handle.read()

        metadata = json.dumps({"file": {"display_name": Path(pdf_path).name}})
        boundary = uuid.uuid4().hex
        body = self._build_related_body(boundary, metadata, file_bytes)
        headers = {"Content-Type": f"multipart/related; boundary={boundary}"}

        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                url,
                data=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise LLMClientError(f"Google upload failed ({resp.status}): {text}")
                payload = json.loads(text)
                file_id = payload.get("file", {}).get("name")
                if not file_id:
                    raise LLMClientError("Google upload succeeded but no file id was returned.")
                # The upload response should already return file_id in the correct format (e.g., "files/xxxxx")
                # Log it for debugging
                logger.debug("Google file upload returned file_id: %s", file_id)
                await self._wait_for_processing(file_id, session=session)
                return file_id

    async def _wait_for_processing(self, file_id: str, *, session: aiohttp.ClientSession | None = None) -> None:
        # File status check must use v1beta (same as upload API)
        status_base = "https://generativelanguage.googleapis.com/v1beta"
        url = f"{status_base}/{file_id}?key={self.api_key}"
        close_session = False
        if session is None:
            connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
            session = aiohttp.ClientSession(connector=connector)
            close_session = True

        start = time.time()
        try:
            while time.time() - start < 90:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    payload = await resp.json()
                    if resp.status != 200:
                        await asyncio.sleep(2)
                        continue
                    state = payload.get("state")
                    if state == "ACTIVE":
                        return
                    if state == "FAILED":
                        raise LLMClientError(
                            f"Google file processing failed: {payload.get('error', {}).get('message', payload)}"
                        )
                await asyncio.sleep(2)
        finally:
            if close_session:
                await session.close()

        raise LLMClientError("Google file processing timeout")

    async def query_with_file(
        self,
        file_id: str | None,
        prompt: str,
        question_data: Optional[dict] = None,
    ) -> str:
        if not self.api_key:
            raise LLMClientError("Google API key missing")
        if not file_id:
            raise LLMClientError("Google client requires uploaded file id")

        # For provider file upload calls, question_data is not needed
        # The prompt already contains all question information
        # question_data is only used by the scorer service, not by provider APIs
        final_prompt = prompt

        # Ensure file_uri is in correct format (should be "files/xxxxx")
        # The upload response should already return it in this format, but verify
        file_uri = file_id
        if not file_uri.startswith("files/"):
            logger.warning("Google file_id missing 'files/' prefix, adding it: %s", file_id)
            file_uri = f"files/{file_id}"

        # Google Gemini API v1beta: Use snake_case for field names
        # file_data, file_uri, mime_type (v1beta format)
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "file_data": {
                                "file_uri": file_uri,
                                "mime_type": "application/pdf"
                            }
                        },
                        {
                            "text": final_prompt
                        }
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
        }

        logger.debug("Google Gemini API call - file_uri: %s, model: %s", file_uri, self.model)
        logger.debug("Google Gemini payload: %s", json.dumps(payload, indent=2))

        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector) as session:
            # For v1beta API, model name should include "models/" prefix in the URL
            model_name = self.model if self.model.startswith("models/") else f"models/{self.model}"
            url = f"{self.base_url}/{model_name}:generateContent?key={self.api_key}"
            logger.debug("Google Gemini API URL: %s", url.replace(self.api_key, "***"))
            
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    try:
                        error_json = json.loads(error_text)
                        error_details = error_json.get("error", {})
                        error_message = error_details.get("message", error_text)
                        error_status = error_details.get("status", "UNKNOWN")
                        logger.error(
                            "Google Gemini API error: status=%d, error_status=%s, message=%s, file_uri=%s, model=%s",
                            resp.status,
                            error_status,
                            error_message,
                            file_uri,
                            self.model,
                        )
                    except Exception:
                        logger.error(
                            "Google Gemini API error: status=%d, body=%s, file_uri=%s, model=%s",
                            resp.status,
                            error_text[:500],
                            file_uri,
                            self.model,
                        )
                    raise LLMClientError(f"Google completion failed ({resp.status}): {error_text}")
                result = await resp.json()
                candidates = result.get("candidates") or []
                if not candidates:
                    raise LLMClientError("Google returned no candidates")
                parts = candidates[0].get("content", {}).get("parts") or []
                if not parts:
                    raise LLMClientError("Google candidate missing parts")
                return parts[0].get("text", "").strip()

    @staticmethod
    def _build_related_body(boundary: str, metadata: str, file_bytes: bytes) -> bytes:
        meta_part = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata}\r\n"
        ).encode("utf-8")
        file_part = (
            f"--{boundary}\r\n"
            "Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8") + file_bytes + b"\r\n"
        closing = f"--{boundary}--\r\n".encode("utf-8")
        return meta_part + file_part + closing


def build_available_clients(
    *,
    openai_key: str | None,
    anthropic_key: str | None,
    google_key: str | None,
    model_overrides: dict[str, str],
    fallback_models: dict[str, str] | None = None,
) -> dict[str, BaseLLMClient]:
    clients: dict[str, BaseLLMClient] = {}
    fallback_models = fallback_models or {}

    openai_client = OpenAIClient(openai_key, model_overrides.get("openai", "gpt-4o-mini"))
    if openai_client.is_configured():
        clients[openai_client.name] = openai_client
    else:
        logger.info("Skipping OpenAI report client - API key missing.")

    # Files API beta requires claude-sonnet-4-5-20250929 or similar models that support file uploads
    anthropic_client = AnthropicClient(
        anthropic_key,
        model_overrides.get("anthropic", "claude-sonnet-4-5-20250929"),
        fallback_model=fallback_models.get("anthropic") or "claude-3-5-sonnet-20241022",
    )
    if anthropic_client.is_configured():
        clients[anthropic_client.name] = anthropic_client
    else:
        logger.info("Skipping Anthropic report client - API key missing.")

    # For v1beta API with file uploads, gemini-2.0-flash-exp is the recommended model
    # Note: v1beta has limited model support - only certain models support file uploads
    # Model name should be without "models/" prefix when passed to client
    # The URL will add "models/" prefix automatically
    default_model = model_overrides.get("google", "gemini-2.0-flash-exp")
    google_client = GoogleClient(google_key, default_model)
    if google_client.is_configured():
        clients[google_client.name] = google_client
    else:
        logger.info("Skipping Google report client - API key missing.")

    return clients
