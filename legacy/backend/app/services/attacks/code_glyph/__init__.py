"""
Code Glyph Attack Implementation (lazy factories)

This package exposes factory functions to obtain Code Glyph components without
creating circular imports. Heavy imports are performed inside functions.
"""

from __future__ import annotations

from typing import Any

import logging

logger = logging.getLogger(__name__)


def get_code_glyph_attack() -> Any:
    """Lazy import factory for CodeGlyphAttack class.
    Returns the class (not an instance) or a stub if unavailable.
    """
    try:
        from .handler import CodeGlyphAttack  # type: ignore
        return CodeGlyphAttack
    except Exception as e:
        logger.warning("[code_glyph] get_code_glyph_attack failed: %s", e)
        class CodeGlyphAttackStub:
            def __init__(self, *args, **kwargs):
                pass
        return CodeGlyphAttackStub


def get_code_glyph_renderer() -> Any:
    """Lazy import factory for the glyph renderer."""
    try:
        from .renderer import CodeGlyphRenderer  # type: ignore
        return CodeGlyphRenderer
    except Exception as e:
        logger.warning("[code_glyph] get_code_glyph_renderer failed: %s", e)
        return None


def get_code_glyph_runtime() -> Any:
    """Lazy import factory for the glyph runtime."""
    try:
        from .runtime import CodeGlyphRuntime  # type: ignore
        return CodeGlyphRuntime
    except Exception as e:
        logger.warning("[code_glyph] get_code_glyph_runtime failed: %s", e)
        return None


__all__ = [
    "get_code_glyph_attack",
    "get_code_glyph_renderer",
    "get_code_glyph_runtime",
]