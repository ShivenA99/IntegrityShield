from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from .mapper import build_unified_mappings
from .fontgen import prepare_font_configs, ensure_pad_fonts_ascii, ensure_common_punctuation_pairs
from .pdfgen import render_attacked_pdf
import logging

logger = logging.getLogger(__name__)


def run_code_glyph_pipeline(
    title: str,
    questions: List[Dict],
    entities_by_qnum: Dict[str, Dict[str, str]],
    assessment_dir: Path,
    *,
    font_mode: str,
    prebuilt_dir: Path,
) -> Dict[str, str]:
    """Run the internalized Code Glyph pipeline and generate artifacts.

    Returns paths to attacked_pdf and metadata json.
    """
    cg_dir = assessment_dir / "code_glyph"
    cg_dir.mkdir(parents=True, exist_ok=True)

    # 1) Build unified mappings for the entire document
    logger.info("[code_glyph.pipeline] Building unified mappings from entities")
    pairs: List[Tuple[str, str]] = build_unified_mappings(entities_by_qnum)
    logger.info("[code_glyph.pipeline] Mappings (%d): %s", len(pairs), pairs)

    # 1.5) Ensure pad fonts (U+2009→ASCII letters/digits) exist
    try:
        from ..config import get_base_font_path  # correct parent package
        base_font_path = get_base_font_path()
    except Exception:
        base_font_path = None
    try:
        n_created = ensure_pad_fonts_ascii(prebuilt_dir, base_font_path)
        if n_created:
            logger.info("[code_glyph.pipeline] Generated %d pad fonts (U+2009→ASCII)", n_created)
    except Exception as e:
        logger.warning("[code_glyph.pipeline] Could not ensure pad fonts: %s", e)

    # 1.6) Ensure common punctuation pairs (ASCII letters/digits/ '-') → en/em dashes, quotes, ellipsis
    try:
        n_punct = ensure_common_punctuation_pairs(prebuilt_dir, base_font_path)
        if n_punct:
            logger.info("[code_glyph.pipeline] Generated %d punctuation pair fonts", n_punct)
    except Exception as e:
        logger.warning("[code_glyph.pipeline] Could not ensure punctuation pairs: %s", e)

    # 2) Prepare font configs (prebuilt references)
    logger.info("[code_glyph.pipeline] Preparing font configs; prebuilt_dir=%s", prebuilt_dir)
    font_configs = prepare_font_configs(pairs, prebuilt_dir)
    logger.info("[code_glyph.pipeline] Font configs prepared: %d", len(font_configs))
    for cfg in font_configs:
        fp = cfg.get("font_path")
        if fp:
            logger.info("[code_glyph.pipeline] Pair font resolved for %s→%s: %s", cfg.get("input"), cfg.get("output"), fp)
        else:
            logger.warning("[code_glyph.pipeline] Missing pair font for %s→%s (prebuilt_dir=%s)", cfg.get("input"), cfg.get("output"), cfg.get("prebuilt_dir"))

    # 3) Render attacked PDF (placeholder renderer for now)
    attacked_pdf_path = cg_dir / "attacked.pdf"
    logger.info("[code_glyph.pipeline] Rendering attacked PDF (per-codepoint mapping mode)")
    render_attacked_pdf(title, questions, entities_by_qnum, attacked_pdf_path, prebuilt_dir)

    # 4) Save metadata
    logger.info("[code_glyph.pipeline] Writing metadata.json")
    meta = {
        "mappings": pairs,
        "prebuilt_dir": str(prebuilt_dir),
        "attacked_pdf_path": str(attacked_pdf_path),
        "metadata_path": str(cg_dir / "metadata.json"),
    }
    with open(cg_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    logger.info("[code_glyph.pipeline] Done; attacked_pdf=%s, metadata=%s", attacked_pdf_path, cg_dir / "metadata.json")
    return meta