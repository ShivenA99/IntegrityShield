from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import fitz

from ..config import NewOCRConfig, summarize_config as summarize_ocr_config
from ..ingestion.pdf_ast_extractor import extract_pdf_ast
from ..vendors.mistral_client import MistralClient
from ..vendors.openai_vision_client import OpenAIVisionClient
from ..fusion.layout_fuser import build_document
from ..fusion.region_detector import detect_hard_regions
from ..markdown.index_map import build_markdown_and_index
from ..qa.diagnostics import get_step_logger, save_json
from ..schema.structured_schema import validate_structured_json
from ..schema.structured_schema import StructuredDoc as _SD  # type: ignore
from .post_fuser import post_fuse_questions

logger = logging.getLogger(__name__)

# Temporary toggle: disable Mistral usage in new OCR
_USE_MISTRAL = False


def _page_to_png_bytes(pdf_path: Path, page_index: int, dpi: int) -> bytes:
	doc = fitz.open(str(pdf_path))
	try:
		page = doc.load_page(page_index)
		scale = dpi / 72.0
		pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
		return pix.tobytes("png")
	finally:
		doc.close()


def _crop_region_png(pdf_path: Path, bbox: List[float], page_index: int, dpi: int) -> bytes:
	doc = fitz.open(str(pdf_path))
	try:
		page = doc.load_page(page_index)
		scale = dpi / 72.0
		mat = fitz.Matrix(scale, scale)
		clip = fitz.Rect(*bbox)
		pix = page.get_pixmap(matrix=mat, alpha=False, clip=clip)
		return pix.tobytes("png")
	finally:
		doc.close()


def _blocks_to_pixel_coords(items: List[Dict[str, Any]], dpi: int) -> List[Dict[str, Any]]:
	# Our bboxes are in PDF points; page image we render at dpi so scale factor is dpi/72
	blocks: List[Dict[str, Any]] = []
	for it in items or []:
		if it.get("type") != "text_block":
			continue
		try:
			x0, y0, x1, y1 = [float(v) for v in it.get("bbox", [])]
			blocks.append({
				"block_id": it.get("id"),
				"bbox_px": [int(round(x0 * dpi / 72.0)), int(round(y0 * dpi / 72.0)), int(round(x1 * dpi / 72.0)), int(round(y1 * dpi / 72.0))],
			})
		except Exception:
			continue
	return blocks


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


def _mark_background_assets(structured: Dict[str, Any], iou_thresh: float = 0.5) -> None:
	doc = structured.get("document", {})
	for page in doc.get("pages", []) or []:
		items: List[Dict[str, Any]] = page.get("items", []) or []
		# Collect question text bboxes and linked asset ids
		q_text_bboxes: List[List[float]] = []
		linked_assets: set[str] = set()
		for it in items:
			if it.get("type") == "text_block":
				if it.get("question_text"):
					q_text_bboxes.append(list(it.get("bbox", [0, 0, 0, 0])))
				# Track assets explicitly linked by non-question text blocks
				if not it.get("question_text") and it.get("linked_asset_id"):
					linked_assets.add(str(it.get("linked_asset_id")))
		# Decide per-asset draw and suppression
		for it in items:
			if it.get("type") in {"image", "figure"}:
				bbox = list(it.get("bbox", [0, 0, 0, 0]))
				aid = str(it.get("asset_id", ""))
				# Default: draw only if explicitly linked or not overlapping question text
				draw = False
				if aid and aid in linked_assets:
					draw = True
				else:
					try:
						if not q_text_bboxes or all(_iou(bbox, qb) < iou_thresh for qb in q_text_bboxes):
							draw = True
					except Exception:
						pass
				it["draw_background"] = bool(draw)
				# Suppress assets that overlap question text significantly and aren't linked
				if not draw and any(_iou(bbox, qb) >= iou_thresh for qb in q_text_bboxes):
					it["suppressed"] = True


def _postprocess_document(pdf_path: Path, structured: Dict[str, Any], assets_dir: Path, *, dpi: int = 300, iou_match: float = 0.8, iou_logo: float = 0.9, phash_max_distance: int = 5, page_area_logo_max: float = 0.02) -> Dict[str, Any]:
	"""Local postprocess: mark question_text, prefer images for non-question text, synthesize crops when needed.
	This mirrors the behavior of the old OCR postprocess without importing it.
	"""
	from PIL import Image  # lazy import

	doc = structured.get("document", {})
	pages = doc.get("pages", [])

	# Build quick lookup for question-linked ids
	question_ids: set[str] = set()
	for q in doc.get("questions", []) or []:
		for cid in q.get("context_ids", []) or []:
			if isinstance(cid, str):
				question_ids.add(cid)

	# Precompute aHash per asset
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
		except Exception:
			return 0

	asset_phash: Dict[str, int] = {}

	for page in pages:
		pidx = int(page.get("page_index", 0))
		width = float(page.get("width", 1.0))
		height = float(page.get("height", 1.0))
		page_area = width * height
		items: List[Dict[str, Any]] = page.get("items", [])
		assets: List[Dict[str, Any]] = [it for it in items if it.get("type") in {"image", "figure", "table"}]
		texts: List[Dict[str, Any]] = [it for it in items if it.get("type") == "text_block"]

		# Dedup assets on same page (IoU + aHash)
		keep_flags = [True] * len(assets)
		for i in range(len(assets)):
			a = assets[i]
			abox = a.get("bbox")
			if not keep_flags[i]:
				continue
			if a.get("asset_id"):
				apath = Path(assets_dir) / a.get("asset_id")
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
						ap = Path(assets_dir) / a.get("asset_id")
						bp = Path(assets_dir) / b.get("asset_id")
						if ap.exists() and bp.exists():
							ha = asset_phash.get(a.get("asset_id")) or _ahash(ap)
							hb = asset_phash.get(b.get("asset_id")) or _ahash(bp)
							asset_phash[a.get("asset_id")] = ha
							asset_phash[b.get("asset_id")] = hb
							similar = (ha ^ hb).bit_count() <= phash_max_distance
					if not similar:
						continue
					b_area = _area(bbox)
					# Logo heuristic
					if min(a_area, b_area) / page_area <= page_area_logo_max and iou >= iou_logo:
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
						# General: keep larger
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

		# Prefer image for non-question text; link best-overlap asset or synthesize crop
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
				try:
					pdf = fitz.open(str(pdf_path))
					page_obj = pdf.load_page(pidx)
					rect = fitz.Rect(tbox)
					scale = dpi / 72.0
					mat = fitz.Matrix(scale, scale)
					pix = page_obj.get_pixmap(matrix=mat, alpha=False, clip=rect)
					syn_name = f"page-{pidx}-syn-{t.get('id')}.png"
					syn_path = Path(assets_dir) / syn_name
					pix.save(str(syn_path))
					# Append as an image item
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
				except Exception:
					t["render_as"] = "text"

	# After blocks are marked, set draw/suppress flags on assets to avoid double paint
	_mark_background_assets(structured)

	structured["document"] = doc
	return structured


def build_structured(assessment_dir: Path, original_pdf_path: Path) -> Dict[str, Any]:
	cfg = NewOCRConfig()
	logdir = Path(assessment_dir) / "new_ocr_logs"
	glog = get_step_logger(logdir, "controller")
	glog.info("[NEW_OCR] Starting build_structured: pdf=%s", original_pdf_path)
	glog.info("[NEW_OCR] Config: %s", summarize_ocr_config())

	assets_dir = Path(assessment_dir) / "assets"
	assets_dir.mkdir(parents=True, exist_ok=True)

	# Step 1: Local AST via PyMuPDF (also used for legacy structurer input)
	ast_doc = extract_pdf_ast(Path(original_pdf_path), assets_dir, dpi=cfg.STRUCTURE_OCR_DPI)
	save_json(logdir, "00_ast_doc", ast_doc)

	# Prepare vendors
	# OpenAI Vision (enabled)
	oai = OpenAIVisionClient()
	# Mistral (disabled by toggle)
	mistral = None

	# Step 2: One-call-per-page ROI OCR (OpenAI only)
	pages_local: List[Dict[str, Any]] = ast_doc.get("document", {}).get("pages", [])
	mistral_blocks_all: List[List[Dict[str, Any]]] = []
	oai_blocks_all: List[List[Dict[str, Any]]] = []
	vlog = get_step_logger(logdir, "vendors")
	for i, page in enumerate(pages_local or []):
		try:
			png_bytes = _page_to_png_bytes(Path(original_pdf_path), i, cfg.STRUCTURE_OCR_DPI)
			blocks_px = _blocks_to_pixel_coords(page.get("items", []) or [], cfg.STRUCTURE_OCR_DPI)
			# OpenAI primary only
			o_out = oai.ocr_page_blocks(png_bytes, blocks_px)
			oai_blocks_all.append(o_out.get("blocks", []))
			vlog.info("[NEW_OCR][VENDOR][OpenAI] page=%d blocks=%d conf=%.3f", i, len(o_out.get("blocks", [])), float(o_out.get("confidence", 0.0)))
			# Mistral disabled; push empty page entry for alignment
			mistral_blocks_all.append([])
		except Exception as e:
			vlog.warning("[NEW_OCR][VENDOR] page=%d ROI OCR failed: %s", i, e)
			oai_blocks_all.append([])
			mistral_blocks_all.append([])

	save_json(logdir, "10_oai_blocks", {"pages": oai_blocks_all})
	save_json(logdir, "11_mistral_blocks", {"pages": mistral_blocks_all})

	# Step 3: Write vendor block markdown into AST text_blocks (prefer OpenAI)
	blk_map_o: Dict[str, str] = {}
	blk_map_m: Dict[str, str] = {}
	for pidx, page in enumerate(pages_local or []):
		for blk in (oai_blocks_all[pidx] if pidx < len(oai_blocks_all) else []) or []:
			bid = str(blk.get("block_id"))
			blk_map_o[bid] = blk.get("markdown", "")
	# No mistral mapping when disabled
	for page in pages_local or []:
		for it in page.get("items", []) or []:
			if it.get("type") != "text_block":
				continue
			bid = str(it.get("id"))
			md = blk_map_o.get(bid) or blk_map_m.get(bid) or it.get("text", "")
			it["markdown"] = md

	# Step 4: Build markdown index maps per block
	for page in pages_local or []:
		page_wrapper = {k: page.get(k) for k in ("page_index", "width", "height", "dpi", "items")}
		build_markdown_and_index(page_wrapper)
	save_json(logdir, "30_markdown_index", {"pages": pages_local})

	# Step 5: Assemble structured doc base (no per-region augmentation needed here)
	structured: Dict[str, Any] = {
		"meta": {
			"source_path": str(original_pdf_path),
			"dpi": int(cfg.STRUCTURE_OCR_DPI),
			"num_pages": len(pages_local or []),
			"extractor_versions": {"pymupdf": "legacy_layout_v1"},
							"vendor_versions": {
					"openai_vision_model": oai.model,
					"mistral_model": "",
				},
		},
		"document": {
			"assessment_id": None,
			"title": None,
			"pages": pages_local,
			"questions": [],
			"source_path": str(original_pdf_path),
		}
	}

	# Compose per-page OpenAI markdown by concatenating block markdowns (read-only signal for post-fuser)
	oai_pages_md: List[Dict[str, Any]] = []
	for page in pages_local or []:
		md_parts: List[str] = []
		for it in page.get("items", []) or []:
			if it.get("type") == "text_block":
				md = (it.get("markdown") or it.get("text") or "").strip()
				if md:
					md_parts.append(md)
		oai_pages_md.append({"page_index": int(page.get("page_index", 0)), "markdown": "\n".join(md_parts)})

	# Step 6: Post-fuse questions/title using GPT (AST-anchored) — pass empty mistral pages
	pf = post_fuse_questions(ast_doc, oai_pages_md, []) or {}
	if pf.get("questions"):
		structured["document"]["title"] = pf.get("title")
		structured["document"]["questions"] = pf.get("questions", [])
		glog.info("[NEW_OCR] Post-fuser populated %d questions", len(structured["document"].get("questions", [])))
	else:
		glog.warning("[NEW_OCR] Post-fuser returned no questions; proceeding without legacy fallback.")

	# Step 7: Local postprocess (prefer images for non-question text, mark question_text)
	try:
		structured = _postprocess_document(Path(original_pdf_path), structured, assets_dir, dpi=int(cfg.STRUCTURE_OCR_DPI))
		save_json(logdir, "40_postprocess", structured)
	except Exception as e:
		glog.warning("[NEW_OCR] Postprocess failed (continuing): %s", e)

	# Step 8: Validate and persist
	try:
		validate_structured_json(structured)
	except Exception:
		pass
	out_path = Path(assessment_dir) / "structured.json"
	with open(out_path, "w", encoding="utf-8") as f:
		json.dump(structured, f, ensure_ascii=False, indent=2)
	glog.info("[NEW_OCR] structured.json written: %s", out_path)

	try:
		save_json(logdir, "99_structured_final", structured)
	except Exception:
		pass

	return structured 