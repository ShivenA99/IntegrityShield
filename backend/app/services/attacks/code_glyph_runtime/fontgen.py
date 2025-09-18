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

    logger.info("[code_glyph.fontgen] Pair font not found for %s→%s under %s", inp, out, prebuilt_dir)
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
            # Attempt on-the-fly generation via prebuilt factory if present
            from ..code_glyph.tooling.prebuilt_font_factory import generate_pair_font  # type: ignore
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
    from ..code_glyph.tooling.prebuilt_font_factory import generate_pair_font  # type: ignore
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


def _ascii_letter_digit_codes() -> List[int]:
    # 0-9, A-Z, a-z, plus ASCII hyphen-minus
    digits = list(range(0x30, 0x3A))
    upper = list(range(0x41, 0x5B))
    lower = list(range(0x61, 0x7B))
    return digits + upper + lower + [0x002D]


def ensure_out_to_in_pairs(prebuilt_dir: Path, base_font_path: Optional[Path], out_codes: List[int], in_codes: List[int]) -> int:
    """Ensure pair fonts exist mapping each out_code → in_code under v3.

    Returns number of new fonts created. Uses prebuilt font factory if available.
    """
    # Force v3 working set
    if prebuilt_dir.name != "v3":
        prebuilt_dir = prebuilt_dir / "v3"
    prebuilt_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    try:
        from ..code_glyph.tooling.prebuilt_font_factory import generate_pair_font  # type: ignore
    except Exception:
        generate_pair_font = None  # type: ignore
    if not base_font_path or not base_font_path.exists() or not generate_pair_font:
        logger.warning("[code_glyph.fontgen] Cannot generate pair fonts (base or factory missing). base=%s", base_font_path)
        return 0
    for oc in out_codes:
        for ic in in_codes:
            out_path = _pair_font_path_for_codes(prebuilt_dir, oc, ic)
            if out_path.exists():
                continue
            ok = False
            try:
                ok = generate_pair_font(str(base_font_path), str(out_path), chr(oc), chr(ic))  # type: ignore
            except Exception as e:
                logger.warning("[code_glyph.fontgen] Failed to generate pair font %s: %s", out_path, e)
            if ok:
                created += 1
                if created % 100 == 0:
                    logger.info("[code_glyph.fontgen] Generated %d out→in punctuation pair fonts so far...", created)
    if created:
        logger.info("[code_glyph.fontgen] Created %d punctuation pair fonts under %s", created, prebuilt_dir)
    return created


def ensure_common_punctuation_pairs(prebuilt_dir: Path, base_font_path: Optional[Path]) -> int:
    """Ensure v3 has coverage for common punctuation targets used in mappings.

    Targets include:
      - Dashes/minus: U+2012, U+2013, U+2014, U+2212, U+2011
      - Quotes: U+2018, U+2019, U+201C, U+201D
      - Ellipsis: U+2026
    """
    punct_in_codes = [
        0x2012, 0x2013, 0x2014, 0x2212, 0x2011,
        0x2018, 0x2019, 0x201C, 0x201D,
        0x2026,
    ]
    out_codes = _ascii_letter_digit_codes()
    return ensure_out_to_in_pairs(prebuilt_dir, base_font_path, out_codes, punct_in_codes)


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    prebuilt_root = Path(os.getenv("PREBUILT_DIR", "backend/data/prebuilt_fonts/DejaVuSans/v3")).resolve()
    base_font = Path(os.getenv("BASE_FONT_PATH", "backend/app/services/attacks/code_glyph/tooling/assets/DejaVuSans.ttf")).resolve()
    include_identity = os.getenv("INCLUDE_IDENTITY", "0").lower() in {"1", "true", "yes"}
    try:
        n = generate_full_ascii_pairs(prebuilt_root, base_font, include_identity=include_identity)
        print(f"Generated {n} fonts under {prebuilt_root}")
    except Exception as e:
        logger.error("ASCII pair generation failed: %s", e) 