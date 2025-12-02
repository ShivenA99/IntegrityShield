from __future__ import annotations

import json
from typing import Any, List


def coerce_response_text(response: Any) -> str:
    """Extract textual content from OpenAI Responses payloads."""
    if not response:
        return ""

    output_text = getattr(response, "output_text", None)
    if output_text:
        if isinstance(output_text, list):
            return "\n".join(str(part) for part in output_text if part).strip()
        return str(output_text).strip()

    output = getattr(response, "output", None)
    if output:
        segments: List[str] = []
        for block in output:
            content = getattr(block, "content", None)
            if isinstance(content, list):
                for chunk in content:
                    json_blob = getattr(chunk, "json", None)
                    if json_blob is not None:
                        try:
                            segments.append(json.dumps(json_blob))
                        except Exception:  # pragma: no cover
                            segments.append(str(json_blob))
                        continue
                    text_value = getattr(chunk, "text", None)
                    if text_value:
                        segments.append(text_value if isinstance(text_value, str) else str(text_value))
            else:
                text_value = getattr(block, "text", None)
                if text_value:
                    segments.append(text_value if isinstance(text_value, str) else str(text_value))
        if segments:
            return "\n".join(seg for seg in segments if seg).strip()

    message = getattr(response, "message", None)
    if message and hasattr(message, "content"):
        content = getattr(message, "content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "\n".join(str(item) for item in content if item).strip()

    return str(response)

