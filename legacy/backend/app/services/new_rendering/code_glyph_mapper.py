from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _find_block(structured: Dict[str, Any], block_id: str) -> Dict[str, Any] | None:
	for page in structured.get("document", {}).get("pages", []) or []:
		for it in page.get("items", []) or []:
			if it.get("id") == block_id:
				return it
	return None


def _add_mapping_to_block(block: Dict[str, Any], input_entity: str, output_entity: str) -> None:
	m = block.setdefault("cg_mappings", [])
	pair = {"input_entity": str(input_entity), "output_entity": str(output_entity)}
	if pair not in m:
		m.append(pair)


def _add_runs_from_index_map(block: Dict[str, Any], input_entity: str, output_entity: str) -> None:
	ix = block.get("index_map") or []
	runs = block.setdefault("cg_runs", [])
	md = (block.get("markdown") or block.get("text") or "")
	start_pos = 0
	while True:
		pos = md.find(input_entity, start_pos)
		if pos == -1:
			break
		md_start = pos
		md_end = pos + len(input_entity)
		for entry in ix:
			es = int(entry.get("md_start", 0)); ee = int(entry.get("md_end", 0))
			if md_start >= ee or md_end <= es:
				continue
			spans: List[Tuple[str, int, int]] = entry.get("spans") or []
			needed_s = md_start - es
			needed_e = md_end - es
			for span_id, s0, e0 in spans:
				span_rel_s = int(s0)
				span_rel_e = int(e0)
				seg_s = max(needed_s, span_rel_s)
				seg_e = min(needed_e, span_rel_e)
				if seg_e > seg_s:
					runs.append({
						"span_id": span_id,
						"in": input_entity,
						"out": output_entity,
						"span_start": seg_s,
						"span_end": seg_e,
					})
		start_pos = md_end


def _project_anchor_to_runs(block: Dict[str, Any], anchor: Dict[str, Any], input_entity: str, output_entity: str) -> None:
	if not anchor:
		return
	ix = block.get("index_map") or []
	md = (block.get("markdown") or block.get("text") or "")
	try:
		cs = int(anchor.get("char_start")); ce = int(anchor.get("char_end"))
		if not (0 <= cs < ce <= len(md)):
			return
	except Exception:
		return
	runs = block.setdefault("cg_runs", [])
	for entry in ix:
		es = int(entry.get("md_start", 0)); ee = int(entry.get("md_end", 0))
		if cs >= ee or ce <= es:
			continue
		spans: List[Tuple[str, int, int]] = entry.get("spans") or []
		need_s = cs - es
		need_e = ce - es
		for span_id, s0, e0 in spans:
			span_rel_s = int(s0)
			span_rel_e = int(e0)
			seg_s = max(need_s, span_rel_s)
			seg_e = min(need_e, span_rel_e)
			if seg_e > seg_s:
				runs.append({
					"span_id": span_id,
					"in": input_entity,
					"out": output_entity,
					"span_start": seg_s,
					"span_end": seg_e,
				})


def project_entities_to_blocks(structured: Dict[str, Any]) -> Dict[str, Any]:
	doc = structured.get("document", {})
	questions = doc.get("questions", []) or []
	attached = 0
	for q in questions:
		ents = q.get("code_glyph_entities") or q.get("entities") or {}
		if not ents:
			continue
		ie = (ents.get("input_entity") or ents.get("entities", {}).get("input_entity")) or ""
		oe = (ents.get("output_entity") or ents.get("entities", {}).get("output_entity")) or ""
		if not ie or not oe:
			continue
		anchors = q.get("anchors") or []
		if isinstance(anchors, dict):
			anchors = [anchors]
		for cid in q.get("context_ids", []) or []:
			blk = _find_block(structured, cid)
			if blk and (blk.get("type") == "text_block"):
				_add_mapping_to_block(blk, ie, oe)
				if anchors:
					for anch in anchors:
						if str(anch.get("block_id")) == str(cid):
							_project_anchor_to_runs(blk, anch, ie, oe)
				else:
					_add_runs_from_index_map(blk, ie, oe)
				attached += 1
	logger.info("[NEW_RENDER][MAP] Attached %d block mappings and runs", attached)
	return structured 