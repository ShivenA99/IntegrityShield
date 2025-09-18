from __future__ import annotations

from pathlib import Path

# This shim re-exports configuration helpers for the code_glyph_runtime package.
# It allows internal modules (e.g., fontgen.py) to use a relative import
# `from .config import get_base_font_path` without depending on top-level layout.

from ..config import get_base_font_path as _get_base_font_path


def get_base_font_path() -> Path | None:
    return _get_base_font_path() 