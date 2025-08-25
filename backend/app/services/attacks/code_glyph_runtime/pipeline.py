from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from .mapper import build_unified_mappings
from .fontgen import prepare_font_configs
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
    metadata = {
        "font_mode": font_mode,
        "prebuilt_dir": str(prebuilt_dir),
        "pairs": pairs,
        "font_configs": font_configs,
        "entities_by_qnum": entities_by_qnum,
    }
    meta_path = cg_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    logger.info("[code_glyph.pipeline] Done; attacked_pdf=%s, metadata=%s", attacked_pdf_path, meta_path)

    return {"attacked_pdf_path": str(attacked_pdf_path), "metadata_path": str(meta_path)} 