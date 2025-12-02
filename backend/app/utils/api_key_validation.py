"""API key validation utilities for testing provider API keys."""

from __future__ import annotations

import asyncio
import ssl
from typing import Optional

import aiohttp

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CONTEXT = ssl.create_default_context()


async def validate_openai_key(api_key: str, max_retries: int = 2) -> tuple[bool, Optional[str]]:
    """Validate OpenAI API key by making a simple test call with retry logic."""
    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(max_retries + 1):
        try:
            connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)

            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return True, None
                    elif resp.status == 401:
                        return False, "Invalid or expired OpenAI API key"
                    elif resp.status == 429:
                        return False, "OpenAI API rate limit exceeded"
                    elif resp.status >= 500:
                        # Server error - retry if we have attempts left
                        if attempt < max_retries:
                            await asyncio.sleep(1)
                            continue
                        return False, "OpenAI API temporarily unavailable"
                    else:
                        error_text = await resp.text()
                        return False, f"API error: {error_text[:200]}"
        except asyncio.TimeoutError:
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            return False, "OpenAI API request timeout"
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            return False, f"Validation error: {str(e)[:200]}"

    return False, "Validation failed after retries"


async def validate_anthropic_key(api_key: str) -> tuple[bool, Optional[str]]:
    """Validate Anthropic API key by making a simple test call."""
    try:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Hi"}]
        }
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return True, None
                elif resp.status == 401:
                    return False, "Invalid API key"
                else:
                    error_text = await resp.text()
                    return False, f"API error: {error_text[:200]}"
    except asyncio.TimeoutError:
        return False, "Request timeout"
    except Exception as e:
        return False, f"Validation error: {str(e)[:200]}"


async def validate_google_key(api_key: str) -> tuple[bool, Optional[str]]:
    """Validate Google/Gemini API key by making a simple test call."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{"text": "Hi"}]
            }]
        }
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return True, None
                elif resp.status == 400:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", {}).get("message", "Invalid API key")
                    if "API key" in error_msg or "invalid" in error_msg.lower():
                        return False, "Invalid API key"
                    return False, error_msg[:200]
                elif resp.status == 401 or resp.status == 403:
                    return False, "Invalid API key"
                else:
                    error_text = await resp.text()
                    return False, f"API error: {error_text[:200]}"
    except asyncio.TimeoutError:
        return False, "Request timeout"
    except Exception as e:
        return False, f"Validation error: {str(e)[:200]}"


async def validate_grok_key(api_key: str) -> tuple[bool, Optional[str]]:
    """Validate Grok/xAI API key by making a simple test call."""
    try:
        url = "https://api.x.ai/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return True, None
                elif resp.status == 401:
                    return False, "Invalid API key"
                else:
                    error_text = await resp.text()
                    return False, f"API error: {error_text[:200]}"
    except asyncio.TimeoutError:
        return False, "Request timeout"
    except Exception as e:
        return False, f"Validation error: {str(e)[:200]}"


async def validate_api_key(provider: str, api_key: str) -> tuple[bool, Optional[str]]:
    """Validate an API key for a given provider."""
    provider = provider.lower()
    
    if provider == "openai":
        return await validate_openai_key(api_key)
    elif provider == "anthropic":
        return await validate_anthropic_key(api_key)
    elif provider == "gemini" or provider == "google":
        return await validate_google_key(api_key)
    elif provider == "grok":
        return await validate_grok_key(api_key)
    else:
        return False, f"Unknown provider: {provider}"

