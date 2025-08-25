from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Optional


def _sanitize_token(t: str) -> str:
    return "".join(ch for ch in t if ch.isalnum() or ch in ("-","_"))


def _find_pair_font(prebuilt_dir: Path, inp: str, out: str) -> Optional[Path]:
    """Best-effort search for a pair font file under prebuilt_dir.

    Tries a few common patterns; returns None if not found.
    """
    if not prebuilt_dir.exists():
        return None
    sin = _sanitize_token(inp)
    sou = _sanitize_token(out)

    candidates: List[Path] = []
    # Pattern 1: <prebuilt>/<inp>_<out>.ttf
    candidates.append(prebuilt_dir / f"{sin}_{sou}.ttf")
    # Pattern 2: <prebuilt>/<inp>-to-<out>.ttf
    candidates.append(prebuilt_dir / f"{sin}-to-{sou}.ttf")
    # Pattern 3: nested scan for any file containing both tokens
    for p in prebuilt_dir.rglob("*.ttf"):
        name = p.name.lower()
        if sin.lower() in name and sou.lower() in name:
            candidates.append(p)
            break

    for c in candidates:
        if c.exists():
            return c
    return None


def prepare_font_configs(pairs: List[Tuple[str, str]], prebuilt_dir: Path) -> List[Dict]:
    """Return a list of font config dicts for each input→output pair.

    Includes a resolved 'font_path' if found under prebuilt_dir.
    """
    configs: List[Dict] = []
    for inp, out in pairs:
        font_path = _find_pair_font(prebuilt_dir, inp, out)
        configs.append({
            "input": inp,
            "output": out,
            "prebuilt_dir": str(prebuilt_dir),
            "font_path": str(font_path) if font_path else "",
        })
    return configs 