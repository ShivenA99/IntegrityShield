"""Service module for interacting with Perplexity API.

Perplexity provides an OpenAI-compatible endpoint when using the `openai` Python
client. To avoid adding that dependency, this module uses `requests`.
Adjust the URL / headers if your account settings differ.
"""
from __future__ import annotations

import os
import requests
from typing import Dict, Any

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_API_BASE = os.getenv("PERPLEXITY_API_BASE", "https://api.perplexity.ai")

HEADERS = {
    "Authorization": f"Bearer {PERPLEXITY_API_KEY}" if PERPLEXITY_API_KEY else "",
    "Content-Type": "application/json",
}

MODEL_NAME = os.getenv("PERPLEXITY_MODEL", "pplx-70b-online")


def call_llm(prompt: str) -> Dict[str, Any]:
    """Send the prompt to Perplexity and return parsed JSON."""
    if not PERPLEXITY_API_KEY:
        raise RuntimeError("PERPLEXITY_API_KEY not set in environment")

    url = f"{PERPLEXITY_API_BASE}/v1/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 512,
    }
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    # Expected OpenAI-style structure
    content = data["choices"][0]["message"]["content"]
    return {
        "raw": data,
        "answer_text": content,
    } 