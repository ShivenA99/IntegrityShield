from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .attack_service import AttackType

logger = logging.getLogger(__name__)


@dataclass
class CropInfo:
    page_index: int
    rect: Tuple[float, float, float, float]
    image_path: Path
    highlights: List[Tuple[float, float, float, float]]  # image-coord rectangles to outline


def _load_structured_doc(structured_json_path: Path) -> Dict[str, Any]:
    with open(structured_json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _collect_context_bboxes(structured_doc: Dict[str, Any], question: Dict[str, Any]) -> Dict[int, List[Tuple[float, float, float, float]]]:
    pages = structured_doc.get('document', {}).get('pages', [])
    # Build lookup: id -> (page_index, bbox)
    id_to_page_and_bbox: Dict[str, Tuple[int, Tuple[float, float, float, float]]] = {}
    for p in pages:
        pidx = int(p.get('page_index', 0))
        for it in p.get('items', []) or []:
            iid = it.get('id')
            if not iid:
                continue
            bbox = it.get('bbox') or [0, 0, 0, 0]
            try:
                x0, y0, x1, y1 = [float(v) for v in bbox]
            except Exception:
                continue
            id_to_page_and_bbox[iid] = (pidx, (x0, y0, x1, y1))

    bboxes_by_page: Dict[int, List[Tuple[float, float, float, float]]] = {}
    for cid in (question.get('context_ids') or []):
        v = id_to_page_and_bbox.get(cid)
        if not v:
            continue
        pidx, rect = v
        bboxes_by_page.setdefault(int(pidx), []).append(rect)
    return bboxes_by_page


def _union_rect(rects: List[Tuple[float, float, float, float]], pad: float = 4.0) -> Tuple[float, float, float, float]:
    if not rects:
        return (0.0, 0.0, 0.0, 0.0)
    x0 = min(r[0] for r in rects) - pad
    y0 = min(r[1] for r in rects) - pad
    x1 = max(r[2] for r in rects) + pad
    y1 = max(r[3] for r in rects) + pad
    return (x0, y0, x1, y1)


def _collect_nearby_images(structured_doc: Dict[str, Any], pidx: int, union_rect: Tuple[float, float, float, float], include_px: float) -> List[Tuple[float, float, float, float]]:
    pages = structured_doc.get('document', {}).get('pages', [])
    images: List[Tuple[float, float, float, float]] = []
    for p in pages:
        if int(p.get('page_index', -1)) != int(pidx):
            continue
        for it in p.get('items', []) or []:
            if it.get('type') not in {'image', 'figure', 'table'}:
                continue
            bbox = it.get('bbox') or [0, 0, 0, 0]
            try:
                x0, y0, x1, y1 = [float(v) for v in bbox]
            except Exception:
                continue
            ux0, uy0, ux1, uy1 = union_rect
            # Expand union by include_px; include images that intersect
            ex = (ux0 - include_px, uy0 - include_px, ux1 + include_px, uy1 + include_px)
            rx0, ry0, rx1, ry1 = ex
            if not (x1 < rx0 or x0 > rx1 or y1 < ry0 or y0 > ry1):
                images.append((x0, y0, x1, y1))
    return images


def _normalize_token(s: str) -> List[str]:
    import re
    tokens = re.findall(r"[\w]+", s.lower())
    return tokens


def _find_entity_highlights(page: fitz.Page, clip_rect: fitz.Rect, entities: List[str]) -> List[Tuple[float, float, float, float]]:
    # Compute word-level boxes inside clip_rect that match any entity phrase (sequence match)
    if not entities:
        return []
    words = page.get_text("words") or []  # (x0,y0,x1,y1, word, block,line,word)
    highlights: List[Tuple[float, float, float, float]] = []
    # Filter words inside clip
    in_clip = [(w, idx) for idx, w in enumerate(words) if fitz.Rect(w[0], w[1], w[2], w[3]).intersects(clip_rect)]
    # Build normalized word list
    norm_words = [(_normalize_token(str(w[4])), fitz.Rect(w[0], w[1], w[2], w[3])) for w, _ in in_clip]
    flat_words = [(str(w[4]), fitz.Rect(w[0], w[1], w[2], w[3])) for w, _ in in_clip]
    # Prepare entities as token lists
    ents_tokens = [_normalize_token(e) for e in entities if e]
    if not ents_tokens:
        return []
    # Build a simple sequence over original words (lower)
    seq = [w[0].lower() for w, _ in flat_words]
    # Sliding window match by characters fallback: we do token-seq match using words split, with tolerance to punctuation via tokens
    for ent in ents_tokens:
        if not ent:
            continue
        L = len(ent)
        if L == 0:
            continue
        # Build a simplified list of tokens per word (first token or empty)
        per_word_tok = [(_normalize_token(w) or [""])[0] for w, _ in flat_words]
        i = 0
        while i <= len(per_word_tok) - L:
            if per_word_tok[i:i+L] == ent:
                # Union boxes of the matching run
                xr0 = min(flat_words[i + k][1].x0 for k in range(L))
                yr0 = min(flat_words[i + k][1].y0 for k in range(L))
                xr1 = max(flat_words[i + k][1].x1 for k in range(L))
                yr1 = max(flat_words[i + k][1].y1 for k in range(L))
                highlights.append((xr0, yr0, xr1, yr1))
                i += L
            else:
                i += 1
    return highlights


def _render_crops_from_source(structured_doc: Dict[str, Any], source_pdf_path: Path, crops_by_page: Dict[int, List[Tuple[float, float, float, float]]], out_dir: Path, qnum: str, *, attack_type: AttackType, entities: Tuple[str, str]) -> List[CropInfo]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(source_pdf_path))
    results: List[CropInfo] = []
    for pidx, rects in crops_by_page.items():
        if not rects:
            continue
        # Include nearby images into union
        union = _union_rect(rects, pad=float(os.getenv("REPORT_CROP_PADDING_PX", "10")))
        near_imgs = _collect_nearby_images(structured_doc, int(pidx), union, include_px=float(os.getenv("REPORT_INCLUDE_NEARBY_IMAGES_PX", "24")))
        all_rects = rects + near_imgs
        urect = _union_rect(all_rects, pad=float(os.getenv("REPORT_CROP_PADDING_PX", "10")))
        try:
            rect = fitz.Rect(*urect)
        except Exception:
            logger.warning("[reference_report] Bad rect for Q%s page %s: %s", qnum, pidx, urect)
            continue
        page = doc.load_page(int(pidx))
        # Render only the clip at higher DPI for clarity
        dpi_scale = float(os.getenv("REPORT_CROP_DPI", "2.0"))
        if dpi_scale <= 0:
            dpi_scale = 2.0
        mat = fitz.Matrix(dpi_scale, dpi_scale)
        try:
            pm = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
            img_path = out_dir / f"Q{qnum}_p{pidx}.png"
            pm.save(str(img_path))
            # Compute word-level highlights for entities when applicable
            hl: List[Tuple[float, float, float, float]] = []
            if attack_type == AttackType.CODE_GLYPH:
                ent_list = [entities[0], entities[1]] if entities else []
                word_boxes = _find_entity_highlights(page, rect, ent_list)
                # Scale to image coordinates
                for bx in word_boxes:
                    x0, y0, x1, y1 = bx
                    hl.append(((x0 - rect.x0) * dpi_scale, (y0 - rect.y0) * dpi_scale, (x1 - rect.x0) * dpi_scale, (y1 - rect.y0) * dpi_scale))
            elif attack_type in {AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP, AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION}:
                # Outline full region subtly
                hl.append((0.0, 0.0, (rect.x1 - rect.x0) * dpi_scale, (rect.y1 - rect.y0) * dpi_scale))
            results.append(CropInfo(page_index=int(pidx), rect=urect, image_path=img_path, highlights=hl))
        except Exception as e:
            logger.warning("[reference_report] Crop render failed for Q%s page %s: %s", qnum, pidx, e)
    doc.close()
    return results


def _format_attack_name(attack_type: AttackType) -> str:
    if attack_type == AttackType.CODE_GLYPH:
        return "Looks-Right, Reads-Wrong"
    if attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP:
        return "Invisible Answer Hint"
    if attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION:
        return "Invisible Answer Block"
    return str(attack_type)


def _compute_correct_answer_label(q: Dict[str, Any], reference_answers: Optional[Dict[str, str]] = None) -> str:
    qn = str(q.get('q_number'))
    if reference_answers and qn in reference_answers and reference_answers[qn]:
        return str(reference_answers[qn])
    # Fall back to inferred fields if present
    cge = q.get('code_glyph_entities') or {}
    ent = cge.get('entities') if isinstance(cge.get('entities'), dict) else cge
    inferred = None
    if isinstance(ent, dict):
        inferred = ent.get('inferred_correct_label')
    # Also check top-level fields populated by wrong_answer_service
    inferred = inferred or q.get('inferred_correct_label')
    return str(inferred) if inferred else "UNKNOWN"


def _extract_trap_for_question(q: Dict[str, Any], attack_type: AttackType) -> str:
    if attack_type == AttackType.CODE_GLYPH:
        return str(q.get('wrong_label') or q.get('wrong_answer') or "")
    if attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP:
        return str(q.get('wrong_label') or q.get('wrong_labels') or q.get('wrong_answer') or "")
    return ""  # prevention has no trap option


def _get_entities(q: Dict[str, Any]) -> Tuple[str, str]:
    cge = q.get('code_glyph_entities') or {}
    ents = cge.get('entities')
    if isinstance(ents, dict):
        return str(ents.get('input_entity') or ''), str(ents.get('output_entity') or '')
    if isinstance(cge, dict):
        return str(cge.get('input_entity') or ''), str(cge.get('output_entity') or '')
    return '', ''


def _draw_cover_page(c: canvas.Canvas, title: str, attack_display: str):
    width, height = letter
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, height - 96, "Reference Report")
    c.setFont("Helvetica", 12)
    if title:
        c.drawString(72, height - 120, f"Assessment: {title}")
    c.drawString(72, height - 140, f"Attack: {attack_display}")
    c.showPage()


def _draw_question_section(c: canvas.Canvas, q: Dict[str, Any], crops: List[CropInfo], attack_type: AttackType, reference_answers: Optional[Dict[str, str]] = None, evaluations: Optional[Dict[str, Any]] = None):
    width, height = letter
    y = height - 72

    qn = str(q.get('q_number'))
    stem = str(q.get('stem_text') or '')
    opts = q.get('options') or {}

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, f"Q{qn}")
    y -= 18

    # Visual crop(s) or fallback notice
    if crops:
        max_img_h = 160
        max_img_w = width - 144
        for i, cr in enumerate(crops[:2]):  # show up to 2 crops per question
            try:
                img = ImageReader(str(cr.image_path))
                iw, ih = img.getSize()
                scale = min(max_img_w / iw, max_img_h / ih)
                w, h = iw * scale, ih * scale
                c.drawImage(img, 72, y - h, width=w, height=h)
                # Draw highlights on top (scaled accordingly)
                if cr.highlights:
                    c.setLineWidth(1)
                    c.setStrokeColorRGB(1, 0.1, 0.1)
                    for hx0, hy0, hx1, hy1 in cr.highlights:
                        # scale highlight to drawn size
                        sx = 72
                        sy = y - h
                        fx = hx0 * scale
                        fy = hy0 * scale
                        fw = (hx1 - hx0) * scale
                        fh = (hy1 - hy0) * scale
                        c.rect(sx + fx, sy + (h - fy - fh), fw, fh, fill=0, stroke=1)
                y -= (h + 8)
            except Exception:
                continue
    else:
        # Fallback: show a subtle placeholder so teacher knows where the visual would be
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(72, y, "[No visual snippet available]")
        y -= 14
        logger.info("[reference_report] No crops for Q%s (missing context_ids or bboxes)", qn)

    # Clean text
    c.setFont("Helvetica", 10)
    # Stem
    for line in (stem.splitlines() or [stem]):
        if y < 120:
            c.showPage(); y = height - 72
        c.drawString(72, y, line[:110])
        y -= 12

    # Options
    if isinstance(opts, dict) and opts:
        for lbl, txt in opts.items():
            if y < 120:
                c.showPage(); y = height - 72
            c.drawString(84, y, f"{lbl}) {txt}"[:110])
            y -= 12

    # Attack-specific guidance and answer highlights
    if y < 160:
        c.showPage(); y = height - 72

    trap = _extract_trap_for_question(q, attack_type)
    correct = _compute_correct_answer_label(q, reference_answers)

    c.setFont("Helvetica-Bold", 10)
    if attack_type == AttackType.CODE_GLYPH:
        inp, out = _get_entities(q)
        if inp or out:
            c.drawString(72, y, f"Key change: AI reads '{inp}' as '{out}'")
            y -= 14
        c.setFont("Helvetica", 10)
        c.drawString(72, y, "Cheat detection answer:")
        c.setFont("Helvetica-Bold", 10); c.drawString(220, y, trap or "UNKNOWN"); y -= 12
        c.setFont("Helvetica", 10)
        c.drawString(72, y, "Correct answer:")
        c.setFont("Helvetica-Bold", 10); c.drawString(220, y, correct)
        y -= 16
        c.setFont("Helvetica", 9)
        c.drawString(72, y, "Tip: Paste this question into your AI tool. If it recommends the cheat answer, flag it.")
        y -= 12
    elif attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP:
        reason = str(q.get('wrong_reason') or '')
        c.setFont("Helvetica", 10)
        c.drawString(72, y, "Cheat detection answer:")
        c.setFont("Helvetica-Bold", 10); c.drawString(220, y, trap or "UNKNOWN"); y -= 12
        if reason:
            c.setFont("Helvetica", 10); c.drawString(72, y, "Reason:"); c.setFont("Helvetica-Bold", 10); c.drawString(220, y, reason[:70]); y -= 12
        c.setFont("Helvetica", 10)
        c.drawString(72, y, "Correct answer:")
        c.setFont("Helvetica-Bold", 10); c.drawString(220, y, correct)
        y -= 16
        c.setFont("Helvetica", 9)
        c.drawString(72, y, "Tip: If AI picks the cheat answer, that's a cheat signal.")
        y -= 12
    elif attack_type == AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION:
        c.setFont("Helvetica", 10)
        c.drawString(72, y, "Expected behavior:")
        c.setFont("Helvetica-Bold", 10); c.drawString(200, y, "AI refuses to answer")
        y -= 16
        c.setFont("Helvetica", 9)
        c.drawString(72, y, "Tip: Paste this question into your AI tool. A refusal indicates the block worked.")
        y -= 12

    # Per-LLM outcomes (if provided later)
    if evaluations and isinstance(evaluations, dict):
        # evaluations = { llm: { per_question: { qn: { chosen, success } }, success_rate } }
        if y < 120:
            c.showPage(); y = height - 72
        c.setFont("Helvetica-Bold", 10); c.drawString(72, y, "AI tool results:"); y -= 12
        c.setFont("Helvetica", 10)
        for llm_name, ev in evaluations.items():
            perq = (ev or {}).get('per_question', {})
            row = perq.get(qn)
            if not row:
                continue
            chosen = str(row.get('chosen') or row.get('ai_answer') or row.get('predicted_label') or row.get('answer') or 'UNKNOWN')
            success = bool(row.get('success') or row.get('attack_successful') or row.get('targeted_hit'))
            status = '✓' if success else '–'
            txt = f"{llm_name}: {chosen}  {status}"
            if y < 84:
                c.showPage(); y = height - 72
            c.drawString(84, y, txt[:110])
            y -= 12

    # Page break between questions if running low on space
    if y < 96:
        c.showPage()


def build_reference_report_pdf(
    questions: List[Dict[str, Any]],
    attacked_pdf_path: Path,
    structured_json_path: Path,
    output_path: Path,
    attack_type: AttackType,
    *,
    title: str = "",
    reference_answers: Optional[Dict[str, str]] = None,
    evaluations: Optional[Dict[str, Any]] = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare assets and crops per question
    assessment_dir = output_path.parent
    assets_dir = assessment_dir / "assets"

    structured_doc = _load_structured_doc(structured_json_path)
    # Determine crop source (prefer original)
    source_path_str = structured_doc.get("document", {}).get("source_path")
    source_pdf_path = Path(source_path_str) if source_path_str else attacked_pdf_path

    # Create the PDF
    c = canvas.Canvas(str(output_path), pagesize=letter)

    _draw_cover_page(c, title=title, attack_display=_format_attack_name(attack_type))

    # For each question, compute crops and render section
    for q in questions:
        qn = str(q.get('q_number'))
        bboxes_by_page = _collect_context_bboxes(structured_doc, q)
        # Reconstruction fallback when no context_ids
        if not any(bboxes_by_page.values()):
            try:
                # Heuristic: match stem and options against text blocks to pick regions
                pages = structured_doc.get('document', {}).get('pages', [])
                stem = (q.get('stem_text') or '').strip()
                opts = q.get('options') or {}
                targets = [stem] + [str(v) for v in (opts.values() if isinstance(opts, dict) else [])]
                for p in pages:
                    pidx = int(p.get('page_index', -1))
                    for it in p.get('items', []) or []:
                        if it.get('type') != 'text_block':
                            continue
                        text = str(it.get('text') or '')
                        if any(t and (t in text) for t in targets if t):
                            bbox = it.get('bbox') or [0, 0, 0, 0]
                            try:
                                x0, y0, x1, y1 = [float(v) for v in bbox]
                            except Exception:
                                continue
                            bboxes_by_page.setdefault(pidx, []).append((x0, y0, x1, y1))
                if not any(bboxes_by_page.values()):
                    logger.info("[reference_report] Q%s: could not reconstruct bboxes; will show text only", qn)
            except Exception as e:
                logger.warning("[reference_report] Q%s: reconstruction failed: %s", qn, e)
        inp, out = _get_entities(q)
        crops = _render_crops_from_source(structured_doc, source_pdf_path, bboxes_by_page, assets_dir, qn, attack_type=attack_type, entities=(inp, out))
        _draw_question_section(c, q, crops, attack_type, reference_answers=reference_answers, evaluations=evaluations)

    # Summary (if evaluations exist)
    if evaluations and isinstance(evaluations, dict):
        c.showPage()
        width, height = letter
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, height - 72, "Summary")
        y = height - 96
        c.setFont("Helvetica", 10)
        for llm_name, ev in evaluations.items():
            rate = (ev or {}).get('success_rate')
            if rate is None:
                continue
            txt = f"{llm_name}: {float(rate):.1f}%"
            c.drawString(84, y, txt)
            y -= 14
            if y < 84:
                c.showPage(); y = height - 72

    c.save()
    return output_path 