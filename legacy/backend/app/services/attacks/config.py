from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple


def get_font_mode() -> str:
    """Return font mode for Code Glyph attack: 'prebuilt' or 'dynamic'. Defaults to 'prebuilt'."""
    return os.getenv("CODE_GLYPH_FONT_MODE", "prebuilt").strip().lower()


def get_prebuilt_dir() -> Path:
    """Return the prebuilt fonts directory for Code Glyph.

    Resolution order:
    1) CODE_GLYPH_PREBUILT_DIR env if set
    2) repo default: backend/data/prebuilt_fonts/DejaVuSans/v3
    """
    env_path = os.getenv("CODE_GLYPH_PREBUILT_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()

    # Default inside repo
    repo_default = Path(__file__).resolve().parents[4] / "backend" / "data" / "prebuilt_fonts" / "DejaVuSans" / "v3"
    return repo_default


def summarize_config() -> Tuple[str, Path]:
    return get_font_mode(), get_prebuilt_dir()


def get_base_font_path() -> Path | None:
    """Return a base TTF font path (DejaVuSans) for embedding.

    Resolution order:
    1) CODE_GLYPH_BASE_FONT env if set
    2) tooling asset at backend/app/services/attacks/code_glyph/tooling/assets/DejaVuSans.ttf if exists
    3) poc font at backend/app/services/attacks/poc_code_glyph/DejaVuSans.ttf if exists (legacy)
    4) None (renderer will fall back to built-in fonts)
    """
    env_path = os.getenv("CODE_GLYPH_BASE_FONT")
    if env_path:
        p = Path(env_path).expanduser()
        return p if p.exists() else None
    # New location
    tool_font = Path(__file__).resolve().parents[1] / "code_glyph" / "tooling" / "assets" / "DejaVuSans.ttf"
    if tool_font.exists():
        return tool_font
    # Legacy location
    poc_font = Path(__file__).resolve().parents[1] / "poc_code_glyph" / "DejaVuSans.ttf"
    if poc_font.exists():
        return poc_font
    return None 