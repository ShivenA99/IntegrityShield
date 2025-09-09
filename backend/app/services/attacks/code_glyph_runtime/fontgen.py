from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


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
            logger.info("[code_glyph.fontgen] Found pair font for %s→%s: %s", inp, out, c)
            return c

    logger.warning("[code_glyph.fontgen] Pair font not found for %s→%s under %s", inp, out, prebuilt_dir)
    return None


def prepare_font_configs(pairs: List[Tuple[str, str]], prebuilt_dir: Path) -> List[Dict]:
    """Return metadata for prebuilt pair fonts for requested pairs (if present)."""
    from .config import get_base_font_path  # lazy
    cfgs: List[Dict] = []
    for inp, out in pairs:
        font_path = _find_pair_font(prebuilt_dir, inp, out)
        cfgs.append({"input": inp, "output": out, "font_path": str(font_path) if font_path else None, "prebuilt_dir": str(prebuilt_dir)})
    return cfgs


def _pair_font_path_for_codes(prebuilt_dir: Path, in_code: int, out_code: int) -> Path:
    return prebuilt_dir / f"map_U+{in_code:04X}_to_U+{out_code:04X}.ttf"


def ensure_pad_fonts_ascii(prebuilt_dir: Path, base_font_path: Optional[Path]) -> int:
    """Ensure pad fonts exist for U+2009 → [A–Z, a–z, 0–9].

    Returns count of fonts found or generated. If generation is not available, logs warnings.
    """
    created = 0
    # Force v3 subdir as requested working set
    if prebuilt_dir.name != "v3":
        prebuilt_dir = prebuilt_dir / "v3"
    if not prebuilt_dir.exists():
        prebuilt_dir.mkdir(parents=True, exist_ok=True)
    # Printable ASCII range U+0020..U+007E
    ascii_targets = list(range(0x0020, 0x007F))
    in_code = 0x2009
    for oc in ascii_targets:
        path = _pair_font_path_for_codes(prebuilt_dir, in_code, oc)
        if path.exists():
            continue
        try:
            # Attempt on-the-fly generation via poc prebuilt factory if present
            from ..poc_code_glyph.prebuilt_font_factory import generate_pair_font  # type: ignore
            if base_font_path and base_font_path.exists():
                ok = generate_pair_font(str(base_font_path), str(path), chr(in_code), chr(oc))
                if ok:
                    created += 1
                    logger.info("[code_glyph.fontgen] Generated pad font %s", path)
                else:
                    logger.warning("[code_glyph.fontgen] Failed to generate pad font %s", path)
            else:
                logger.warning("[code_glyph.fontgen] Skipping pad font gen; base font missing: %s", base_font_path)
        except Exception as e:
            logger.warning("[code_glyph.fontgen] Could not generate pad font for U+2009→U+%04X: %s", oc, e)
    return created


def generate_full_ascii_pairs(prebuilt_dir: Path, base_font_path: Path, *, include_identity: bool = False) -> int:
    """Generate fonts mapping every printable ASCII input (U+0020..U+007E) to every printable ASCII output.

    If include_identity is False, skip in==out since base font can handle identity.
    Returns count of fonts generated (newly created).
    """
    # Force v3 subdir as requested working set
    if prebuilt_dir.name != "v3":
        prebuilt_dir = prebuilt_dir / "v3"
    prebuilt_dir.mkdir(parents=True, exist_ok=True)
    if not base_font_path or not base_font_path.exists():
        raise FileNotFoundError(f"Base font not found: {base_font_path}")
    from ..poc_code_glyph.prebuilt_font_factory import generate_pair_font  # type: ignore
    ascii_codes = list(range(0x0020, 0x007F))
    created = 0
    for ic in ascii_codes:
        for oc in ascii_codes:
            if not include_identity and ic == oc:
                continue
            out_path = _pair_font_path_for_codes(prebuilt_dir, ic, oc)
            if out_path.exists():
                continue
            ok = generate_pair_font(str(base_font_path), str(out_path), chr(ic), chr(oc))
            if ok:
                created += 1
                if created % 200 == 0:
                    logger.info("[code_glyph.fontgen] Generated %d ASCII pair fonts so far...", created)
            else:
                logger.warning("[code_glyph.fontgen] Failed to generate pair font %s", out_path)
    logger.info("[code_glyph.fontgen] Finished generating ASCII pair fonts. New fonts: %d", created)
    return created


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    prebuilt_root = Path(os.getenv("PREBUILT_DIR", "backend/data/prebuilt_fonts/DejaVuSans/v3")).resolve()
    base_font = Path(os.getenv("BASE_FONT_PATH", "backend/app/services/attacks/poc_code_glyph/DejaVuSans.ttf")).resolve()
    include_identity = os.getenv("INCLUDE_IDENTITY", "0").lower() in {"1", "true", "yes"}
    try:
        n = generate_full_ascii_pairs(prebuilt_root, base_font, include_identity=include_identity)
        print(f"Generated {n} fonts under {prebuilt_root}")
    except Exception as e:
        logger.error("ASCII pair generation failed: %s", e) 