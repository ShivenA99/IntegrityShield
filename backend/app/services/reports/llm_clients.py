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
from ..llm_clients.rate_limiter import with_exponential_backoff

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

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
    async def upload_file(self, pdf_path: str) -> str:
        # OpenAI combines upload + query; we return the original path
        if not Path(pdf_path).exists():
            raise LLMClientError(f"PDF not found at {pdf_path}")
        return pdf_path

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
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

            max_completion_tokens = 3200
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
                "max_tokens": max_completion_tokens,
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

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
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

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
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

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
    async def upload_file(self, pdf_path: str) -> Optional[str]:
        if not self.api_key:
            raise LLMClientError("Google API key missing")

        # Use the correct upload endpoint: /upload/v1beta/files (not /v1beta/files)
        # Use resumable upload protocol as per Google Gemini API documentation
        upload_base = "https://generativelanguage.googleapis.com/upload/v1beta"
        initiate_url = f"{upload_base}/files?key={self.api_key}"
        
        file_size = Path(pdf_path).stat().st_size
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)

        async with aiohttp.ClientSession(connector=connector) as session:
            # Step 1: Initiate the upload with metadata
            metadata = {
                "file": {
                    "displayName": Path(pdf_path).name
                }
            }
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(file_size),
                "X-Goog-Upload-Header-Content-Type": "application/pdf",
            }
            
            async with session.post(
                initiate_url,
                headers=headers,
                json=metadata,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as init_resp:
                if init_resp.status != 200:
                    error_text = await init_resp.text()
                    raise LLMClientError(f"Google upload initiation failed ({init_resp.status}): {error_text}")
                
                upload_url = init_resp.headers.get("X-Goog-Upload-Url")
                if not upload_url:
                    raise LLMClientError("Google upload initiation succeeded but no upload URL was returned.")
            
            # Step 2: Upload the file
            upload_headers = {
                "Content-Type": "application/pdf",
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "upload, finalize",
                "X-Goog-Upload-Offset": "0",
            }
            
            with open(pdf_path, "rb") as handle:
                file_data = handle.read()
                async with session.post(
                    upload_url,
                    headers=upload_headers,
                    data=file_data,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as upload_resp:
                    if upload_resp.status != 200:
                        error_text = await upload_resp.text()
                        raise LLMClientError(f"Google file upload failed ({upload_resp.status}): {error_text}")
                    
                    try:
                        payload = await upload_resp.json()
                    except Exception as e:
                        error_text = await upload_resp.text()
                        raise LLMClientError(f"Google upload returned invalid JSON: {error_text[:200]}")
                    
                    file_id = payload.get("file", {}).get("name")
                    if not file_id:
                        # Try alternative response format
                        file_id = payload.get("file", {}).get("uri", "").split("/")[-1] if payload.get("file", {}).get("uri") else None
                        if file_id and not file_id.startswith("files/"):
                            file_id = f"files/{file_id}"
                    
                    if not file_id:
                        raise LLMClientError(f"Google upload succeeded but no file id was returned. Response: {json.dumps(payload, indent=2)}")
                    
                    # Ensure file_id is in correct format (files/xxxxx)
                    if not file_id.startswith("files/"):
                        logger.warning("Google file_id missing 'files/' prefix, adding it: %s", file_id)
                        file_id = f"files/{file_id}"
                    
                    logger.debug("Google file upload returned file_id: %s", file_id)
                    await self._wait_for_processing(file_id, session=session)
                    return file_id

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
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

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
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
                    "role": "user",
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
                        error_code = error_details.get("code", resp.status)
                        logger.error(
                            "Google Gemini API error: status=%d, error_status=%s, error_code=%s, message=%s, file_uri=%s, model=%s",
                            resp.status,
                            error_status,
                            error_code,
                            error_message,
                            file_uri,
                            self.model,
                        )
                        # Raise LLMClientError with detailed message
                        raise LLMClientError(
                            f"Google completion failed ({resp.status}): {error_status} - {error_message}"
                        )
                    except LLMClientError:
                        raise  # Re-raise LLMClientError
                    except Exception:
                        logger.error(
                            "Google Gemini API error: status=%d, body=%s, file_uri=%s, model=%s",
                            resp.status,
                            error_text[:500],
                            file_uri,
                            self.model,
                        )
                        raise LLMClientError(
                            f"Google completion failed ({resp.status}): {error_text[:200]}"
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


class GrokClient(BaseLLMClient):
    """Grok client using xAI API (OpenAI-compatible interface)."""
    name = "grok"

    def __init__(self, api_key: str | None, model: str) -> None:
        super().__init__(api_key, model)
        self.base_url = "https://api.x.ai/v1"

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
    async def upload_file(self, pdf_path: str) -> str:
        # Grok uses OpenAI-compatible API, so we return the original path
        # The file will be uploaded as part of the query_with_file call
        if not Path(pdf_path).exists():
            raise LLMClientError(f"PDF not found at {pdf_path}")
        return pdf_path

    @with_exponential_backoff(max_retries=3, base_delay=1.0, max_delay=60.0)
    async def query_with_file(
        self,
        file_id: str | None,
        prompt: str,
        question_data: Optional[dict] = None,
    ) -> str:
        if not self.api_key:
            raise LLMClientError("Grok API key missing")

        pdf_path = file_id or ""
        if not pdf_path:
            raise LLMClientError("Grok requires the original pdf path reference")

        # Grok uses OpenAI-compatible API
        upload_url = f"{self.base_url}/files"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)

        async with aiohttp.ClientSession(connector=connector) as session:
            # Upload file - xAI Grok uses OpenAI-compatible API
            # Note: xAI may not support file uploads yet - if this fails, we'll get a clear error
            try:
                with open(pdf_path, "rb") as handle:
                    data = aiohttp.FormData()
                    data.add_field("file", handle, filename=Path(pdf_path).name, content_type="application/pdf")
                    data.add_field("purpose", "user_data")
                    async with session.post(upload_url, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            # Check if xAI doesn't support file uploads
                            if resp.status == 404 or "not found" in error_text.lower() or "not supported" in error_text.lower():
                                raise LLMClientError(
                                    f"Grok file upload not supported (status {resp.status}): {error_text[:200]}. "
                                    "xAI Grok may not support file uploads yet."
                                )
                            raise LLMClientError(f"Grok upload failed (status {resp.status}): {error_text[:200]}")
                        try:
                            payload = await resp.json()
                        except json.JSONDecodeError:
                            error_text = await resp.text()
                            raise LLMClientError(f"Grok upload returned invalid JSON: {error_text[:200]}")
                        actual_file_id = payload.get("id")
                        if not actual_file_id:
                            raise LLMClientError("Grok upload succeeded but no file id was returned.")
            except LLMClientError:
                raise  # Re-raise LLMClientError
            except Exception as e:
                raise LLMClientError(f"Grok file upload error: {str(e)}")

            # Wait for file processing
            file_status_url = f"{self.base_url}/files/{actual_file_id}"
            start = time.time()
            while time.time() - start < 90:
                async with session.get(file_status_url, headers=headers) as status_resp:
                    if status_resp.status == 200:
                        file_state = await status_resp.json()
                        if file_state.get("status") == "processed":
                            break
                        if file_state.get("status") == "error":
                            raise LLMClientError(f"Grok file processing failed: {file_state}")
                await asyncio.sleep(2)
            else:
                raise LLMClientError("Grok file processing timeout")

            # Query with file
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
                "max_tokens": 3200,
            }

            async with session.post(
                f"{self.base_url}/chat/completions",
                headers={**headers, "Content-Type": "application/json"},
                data=json.dumps(completion_payload),
                timeout=aiohttp.ClientTimeout(total=180),
            ) as completion_resp:
                if completion_resp.status != 200:
                    raise LLMClientError(f"Grok completion failed: {await completion_resp.text()}")
                result = await completion_resp.json()
                choices = result.get("choices") or []
                if not choices:
                    raise LLMClientError("Grok returned no choices")
                return choices[0]["message"]["content"].strip()


def build_available_clients(
    *,
    openai_key: str | None,
    anthropic_key: str | None,
    google_key: str | None,
    grok_key: str | None = None,
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

    # Enable Google/Gemini client
    # For v1beta API with file uploads, gemini-2.0-flash-exp or gemini-2.5-flash is recommended
    # Note: v1beta has limited model support - only certain models support file uploads
    # Model name should be without "models/" prefix when passed to client
    # The URL will add "models/" prefix automatically
    default_model = model_overrides.get("google", "gemini-2.5-flash")
    google_client = GoogleClient(google_key, default_model)
    if google_client.is_configured():
        clients[google_client.name] = google_client
    else:
        logger.info("Skipping Google report client - API key missing.")

    # Add Grok client (xAI - OpenAI-compatible API)
    grok_client = GrokClient(grok_key, model_overrides.get("grok", "grok-2-latest"))
    if grok_client.is_configured():
        clients[grok_client.name] = grok_client
    else:
        logger.info("Skipping Grok report client - API key missing.")

    return clients
