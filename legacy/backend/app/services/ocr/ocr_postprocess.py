from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def _area(b: List[float]) -> float:
    return max(0.0, (b[2] - b[0])) * max(0.0, (b[3] - b[1]))


def _iou(a: List[float], b: List[float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def _contains(outer: List[float], inner: List[float], tol: float = 0.0) -> bool:
    return inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol


def _ahash(path: Path, hash_size: int = 8) -> int:
    try:
        with Image.open(path) as im:
            im = im.convert("L").resize((hash_size, hash_size))
            pixels = list(im.getdata())
            avg = sum(pixels) / len(pixels)
            bits = 0
            for i, p in enumerate(pixels):
                if p >= avg:
                    bits |= (1 << i)
            return bits
    except Exception as e:
        logger.debug("[ocr_postprocess] ahash failed for %s: %s", path, e)
        return 0


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def postprocess_document(
    pdf_path: Path,
    layout_doc: Dict[str, Any],
    assets_dir: Path,
    *,
    questions: Optional[List[Dict[str, Any]]] = None,
    dpi: int = 300,
    iou_match: float = 0.8,
    iou_logo: float = 0.9,
    phash_max_distance: int = 5,
    page_area_logo_max: float = 0.02,
) -> Dict[str, Any]:
    """Deduplicate overlapping assets, mark question text, and prefer image for non-question text.

    - Suppress duplicate assets on the same page using IoU + aHash.
    - Mark text blocks referenced by questions (via context_ids) as question_text=True.
    - For non-question text blocks: if sufficiently overlapped by an asset, set render_as=image and link it.
      Otherwise, create a synthetic crop at the text bbox and link that as an image.
    """
    assets_dir = Path(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)

    doc = layout_doc.get("document", {})
    pages = doc.get("pages", [])

    # Build quick lookup of page dims
    page_dims: Dict[int, Tuple[float, float]] = {p.get("page_index"): (p.get("width"), p.get("height")) for p in pages}

    # Prepare question-linked IDs (from context_ids)
    question_ids: set[str] = set()
    if questions:
        for q in questions:
            for cid in q.get("context_ids", []) or []:
                question_ids.add(cid)

    # Precompute aHash for existing assets
    asset_phash: Dict[str, int] = {}

    for page in pages:
        pidx = page.get("page_index")
        width, height = page_dims.get(pidx, (1.0, 1.0))
        page_area = width * height

        items: List[Dict[str, Any]] = page.get("items", [])
        # Split into assets and text blocks
        assets: List[Dict[str, Any]] = [it for it in items if it.get("type") in {"image", "figure", "table"}]
        texts: List[Dict[str, Any]] = [it for it in items if it.get("type") == "text_block"]

        # Deduplicate assets on same page
        keep_flags = [True] * len(assets)
        for i in range(len(assets)):
            a = assets[i]
            abox = a.get("bbox")
            if not keep_flags[i]:
                continue
            # Compute aHash for a
            if a.get("asset_id"):
                apath = assets_dir / a.get("asset_id")
                if apath.exists():
                    asset_phash.setdefault(a.get("asset_id"), _ahash(apath))
            a_area = _area(abox)
            for j in range(i + 1, len(assets)):
                if not keep_flags[j]:
                    continue
                b = assets[j]
                bbox = b.get("bbox")
                iou = _iou(abox, bbox)
                if iou >= iou_match:
                    # Compare by aHash if available
                    similar = True
                    if a.get("asset_id") and b.get("asset_id"):
                        ap = assets_dir / a.get("asset_id")
                        bp = assets_dir / b.get("asset_id")
                        if ap.exists() and bp.exists():
                            ha = asset_phash.get(a.get("asset_id")) or _ahash(ap)
                            hb = asset_phash.get(b.get("asset_id")) or _ahash(bp)
                            asset_phash[a.get("asset_id")] = ha
                            asset_phash[b.get("asset_id")] = hb
                            similar = _hamming(ha, hb) <= phash_max_distance
                    if not similar:
                        continue
                    # Decide which to keep
                    b_area = _area(bbox)
                    # Logo heuristic: keep smaller if very small
                    if min(a_area, b_area) / page_area <= page_area_logo_max and iou >= iou_logo:
                        # Keep the smaller, suppress the larger (prefer tight logo crop)
                        if a_area <= b_area:
                            keep_flags[j] = False
                            b["suppressed"] = True
                            b["suppression_reason"] = "overlap_duplicate_logo"
                            b["parent_id"] = a.get("id")
                        else:
                            keep_flags[i] = False
                            a["suppressed"] = True
                            a["suppression_reason"] = "overlap_duplicate_logo"
                            a["parent_id"] = b.get("id")
                            break
                    else:
                        # General: keep the larger area
                        if a_area >= b_area:
                            keep_flags[j] = False
                            b["suppressed"] = True
                            b["suppression_reason"] = "overlap_duplicate"
                            b["parent_id"] = a.get("id")
                        else:
                            keep_flags[i] = False
                            a["suppressed"] = True
                            a["suppression_reason"] = "overlap_duplicate"
                            a["parent_id"] = b.get("id")
                            break

        # Mark question text
        for t in texts:
            t["question_text"] = t.get("id") in question_ids

        # Prefer image for non-question text; link best-overlap asset
        for t in texts:
            if t.get("question_text"):
                t["render_as"] = "text"
                continue
            tbox = t.get("bbox")
            best = None
            best_iou = 0.0
            for a in assets:
                if a.get("suppressed"):
                    continue
                iou = _iou(tbox, a.get("bbox"))
                if iou > best_iou:
                    best_iou = iou
                    best = a
            if best and (best_iou >= iou_match or _contains(best.get("bbox"), tbox) or _contains(tbox, best.get("bbox"))):
                t["render_as"] = "image"
                t["linked_asset_id"] = best.get("asset_id")
            else:
                # Synthetic crop
                try:
                    page_obj = None
                    # Render only this page
                    pdf = fitz.open(str(pdf_path))
                    page_obj = pdf.load_page(pidx)
                    rect = fitz.Rect(tbox)
                    scale = dpi / 72.0
                    mat = fitz.Matrix(scale, scale)
                    pix = page_obj.get_pixmap(matrix=mat, alpha=False, clip=rect)
                    syn_name = f"page-{pidx}-syn-{t.get('id')}.png"
                    syn_path = assets_dir / syn_name
                    pix.save(str(syn_path))
                    # Append as an image item so renderer can place it later
                    syn_item = {
                        "id": f"p{pidx}-syn-{t.get('id')}",
                        "type": "image",
                        "bbox": list(tbox),
                        "bbox_norm": t.get("bbox_norm"),
                        "asset_id": syn_name,
                        "orig_mime": "image/png",
                        "synthetic": True,
                    }
                    page["items"].append(syn_item)
                    t["render_as"] = "image"
                    t["linked_asset_id"] = syn_name
                    pdf.close()
                except Exception as e:
                    logger.debug("[ocr_postprocess] Synthetic crop failed for %s: %s", t.get("id"), e)
                    t["render_as"] = "text"

        # Prefer image over figure where both overlap a text block: already handled via best-overlap selection

    layout_doc["document"] = doc
    return layout_doc 