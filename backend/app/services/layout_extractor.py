from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def _normalize_bbox(bbox: Tuple[float, float, float, float], width: float, height: float) -> List[float]:
    x0, y0, x1, y1 = bbox
    return [x0 / width, y0 / height, x1 / width, y1 / height]


def _as_rect(bbox: Tuple[float, float, float, float]) -> fitz.Rect:
    return fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])


def extract_layout_and_assets(pdf_path: Path, out_assets_dir: Path, dpi: int = 300) -> Dict[str, Any]:
    """Extract layout (text blocks) and raster crops (images/tables/figures) from a PDF.

    - Text blocks are collected from page.get_text('dict') with their bounding boxes.
    - Images are cropped from page raster using image block bboxes found in raw dict.
    - Vector drawings are grouped by page and rasterized into one or more figure crops (heuristic).
    - Tables are heuristically detected as dense drawing clusters; initially, we emit drawings as 'figure'.

    Returns a structured document dict suitable for writing to structured.json.
    """
    pdf_path = Path(pdf_path)
    out_assets_dir = Path(out_assets_dir)
    out_assets_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    logger.info("[layout_extractor] Opened PDF: %s with %d pages", pdf_path, doc.page_count)

    document: Dict[str, Any] = {
        "assessment_id": None,
        "title": None,
        "pages": [],
    }

    # Scale for raster crops
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)

    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        width, height = page.rect.width, page.rect.height
        logger.info("[layout_extractor] Page %d: size %.1fx%.1f", page_index + 1, width, height)

        page_item_list: List[Dict[str, Any]] = []

        # 1) Text blocks via 'dict' structure
        text_dict = page.get_text("dict") or {}
        for bi, block in enumerate(text_dict.get("blocks", [])):
            if block.get("type", 0) != 0:
                continue  # non-text in this structure
            bbox = tuple(block.get("bbox", (0, 0, 0, 0)))
            lines = block.get("lines", [])
            text_parts: List[str] = []
            for line in lines:
                spans = line.get("spans", [])
                for sp in spans:
                    txt = sp.get("text", "")
                    if txt:
                        text_parts.append(txt)
                # Preserve line breaks
                text_parts.append("\n")
            text = "".join(text_parts).strip()
            if not text:
                continue
            item = {
                "id": f"p{page_index}-tb{bi}",
                "type": "text_block",
                "bbox": list(bbox),
                "bbox_norm": _normalize_bbox(bbox, width, height),
                "text": text,
            }
            page_item_list.append(item)

        # 2) Images via 'rawdict' image blocks + raster crop
        raw = page.get_text("rawdict") or {}
        image_blocks = []
        for bi, block in enumerate(raw.get("blocks", [])):
            if block.get("type") == 1:  # image
                bbox = tuple(block.get("bbox", (0, 0, 0, 0)))
                image_blocks.append((bi, bbox))
        logger.info("[layout_extractor] Page %d: found %d image blocks", page_index + 1, len(image_blocks))

        # Render and crop each image area directly using clip rectangles
        for ib_idx, (bi, bbox) in enumerate(image_blocks):
            rect = _as_rect(bbox)
            subpix = page.get_pixmap(matrix=matrix, alpha=False, clip=rect)
            asset_name = f"page-{page_index}-img-{ib_idx}.png"
            asset_path = out_assets_dir / asset_name
            subpix.save(str(asset_path))
            item = {
                "id": f"p{page_index}-im{ib_idx}",
                "type": "image",
                "bbox": list(bbox),
                "bbox_norm": _normalize_bbox(bbox, width, height),
                "asset_id": str(asset_path.name),
                "orig_mime": "image/png",
            }
            page_item_list.append(item)

        # 3) Drawings (figures) via get_drawings(); simple grouping: one figure per page bounding all drawings
        drawings = page.get_drawings()
        if drawings:
            # Compute union bbox of drawings
            xs: List[float] = []
            ys: List[float] = []
            for d in drawings:
                rect = d.get("rect")
                if rect:
                    xs.extend([rect.x0, rect.x1])
                    ys.extend([rect.y0, rect.y1])
            if xs and ys:
                bbox = (min(xs), min(ys), max(xs), max(ys))
                clip = fitz.Rect(bbox)
                subpix = page.get_pixmap(matrix=matrix, alpha=False, clip=clip)
                asset_name = f"page-{page_index}-fig-0.png"
                asset_path = out_assets_dir / asset_name
                subpix.save(str(asset_path))
                item = {
                    "id": f"p{page_index}-fig0",
                    "type": "figure",
                    "bbox": list(bbox),
                    "bbox_norm": _normalize_bbox(bbox, width, height),
                    "asset_id": str(asset_path.name),
                    "orig_mime": "image/png",
                }
                page_item_list.append(item)
                logger.info("[layout_extractor] Page %d: drawings crop saved as %s", page_index + 1, asset_name)

        # Assemble page
        page_entry = {
            "page_index": page_index,
            "width": width,
            "height": height,
            "dpi": dpi,
            "items": page_item_list,
        }
        document["pages"].append(page_entry)

    doc.close()

    result = {"document": document}
    logger.info("[layout_extractor] Extraction complete: %d pages", len(document["pages"]))
    for p in document["pages"]:
        logger.info(
            "[layout_extractor] Page %d: %d items", p["page_index"] + 1, len(p.get("items", []))
        )
    return result 