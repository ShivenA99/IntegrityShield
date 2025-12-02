from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import fitz
from sqlalchemy import text

from ...extensions import db
from ...models import CharacterMapping, QuestionManipulation, PipelineRun
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.manipulation.context_aware_processor import ContextAwareProcessor
from ...services.manipulation.substring_manipulator import SubstringManipulator
from ...services.manipulation.universal_character_mapper import MappingResult, UniversalCharacterMapper
from ...services.manipulation.visual_fidelity_validator import VisualFidelityValidator
from ...services.manipulation.effectiveness import aggregate_effectiveness
from ...services.integration.external_api_client import ExternalAIClient
from ...services.ai_clients.openai_vision_client import OpenAIVisionClient
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from ...services.pipeline.auto_mapping_strategy import (
    TARGET_STRATEGY_TYPES,
    SIGNAL_STRATEGY_TYPES,
    StrategyDefinition,
    build_generation_prompt,
    build_index_reference,
    describe_strategy_for_validation,
    generate_heuristic_mappings,
    get_strategy,
)
from .enhancement_methods.base_renderer import BaseRenderer
from .enhancement_methods.span_extractor import SpanRecord, collect_span_records
from ...services.validation.gpt5_validation_service import GPT5ValidationService, ValidationResult
from ...services.mapping.mapping_staging_service import MappingStagingService


@dataclass
class AutoMappingOutcome:
	prompt: str
	provider: str
	raw_content: str
	raw_response: Optional[Dict[str, Any]]
	parsed_payload: Dict[str, Any]
	enriched_mappings: List[Dict[str, Any]]
	inferred_ranges: List[Dict[str, Any]]
	skipped_entries: List[Dict[str, Any]]
	strategy_used: str
	fallback_used: bool
	strategy_validation_focus: str
	attempt_logs: List[Dict[str, Any]] = field(default_factory=list)
	prompt_history: List[str] = field(default_factory=list)
	selected_candidate_rank: Optional[int] = None
	selected_round: Optional[int] = None
	retries_used: int = 0


@dataclass
class GenerationCallResult:
	result: Dict[str, Any]
	raw_response: Optional[Dict[str, Any]]
	raw_content: str
	parsed_payload: Dict[str, Any]
	mappings_payload: List[Dict[str, Any]]
	fallback_used: bool
	strategy_used: Optional[str]
	provider_used: str


class SmartSubstitutionService:
	def __init__(self) -> None:
		self.logger = get_logger(__name__)
		self.structured_manager = StructuredDataManager()
		self.mapper = UniversalCharacterMapper()
		self.substrings = SubstringManipulator()
		self.validator = VisualFidelityValidator()
		self.context_processor = ContextAwareProcessor()
		self.staging_service = MappingStagingService()
		self.ai_client = ExternalAIClient()
		self.vision_client = OpenAIVisionClient()
		self._vision_geometry_scale = self._resolve_float_env("VISION_GEOMETRY_SCALE", 2.0, minimum=0.5)
		self._vision_geometry_margin = self._resolve_float_env("VISION_GEOMETRY_MARGIN", 8.0, minimum=0.0)

	def refresh_geometry_for_run(self, run_id: str) -> int:
		"""Re-run Vision geometry enrichment for all mappings in a run.

		Returns the number of questions updated.
		"""
		structured = self.structured_manager.load(run_id)
		if not structured:
			return 0

		questions_models = (
			QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
			.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
			.all()
		)
		if not questions_models:
			return 0

		updated = 0
		for model in questions_models:
			if not model.substring_mappings:
				continue

			try:
				structured_question = self._get_structured_question(run_id, model.question_number, structured)
				normalized = [self._normalize_mapping_entry(entry) for entry in list(model.substring_mappings or [])]
				if not normalized:
					continue
				has_geometry = all(
					entry.get("selection_page") is not None
					and entry.get("selection_bbox")
					for entry in normalized
				)
				is_validated = all(bool(entry.get("validated")) for entry in model.substring_mappings or [])
				if has_geometry and is_validated:
					continue

				enriched = self._enrich_selection_geometry(run_id, model, normalized, force_refresh=False)
				if enriched != model.substring_mappings:
					model.substring_mappings = enriched
					updated += 1
					self.logger.info(
						"vision geometry refreshed",
						run_id=run_id,
						question_number=model.question_number,
						mappings=len(enriched),
					)
				db.session.add(model)
			except Exception as exc:  # noqa: BLE001
				self.logger.warning(
					"geometry refresh failed",
					run_id=run_id,
					question_number=model.question_number,
					error=str(exc),
				)

		db.session.commit()
		return updated

	def rebuild_mapping_geometry(
		self,
		run_id: str,
		*,
		question_numbers: Optional[Iterable[str]] = None,
		force_refresh: bool = True,
	) -> int:
		"""Clear cached geometry for targeted mappings and rebuild it deterministically."""

		labels: Optional[set[str]] = None
		if question_numbers is not None:
			labels = {str(label).strip() for label in question_numbers if str(label).strip()}
			if not labels:
				return 0

		query = (
			QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
			.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
		)
		if labels:
			query = query.filter(QuestionManipulation.question_number.in_(labels))

		models = query.all()
		if not models:
			return 0

		geometry_keys = {
			"selection_page",
			"selection_bbox",
			"selection_quads",
			"selection_span_ids",
			"span_ids",
			"matched_glyph_path",
			"geometry_source",
			"vision_confidence",
			"matched_fingerprint_key",
			"fingerprint",
			"rewrite_left_overflow",
			"rewrite_right_overflow",
			"rewrite_scale",
			"rewrite_font_size",
			"rewrite_font_name",
		}

		updated = 0
		for model in models:
			existing_list = list(model.substring_mappings or [])
			if not existing_list:
				continue

			sanitized_entries: List[Dict[str, Any]] = []
			removed_any = False
			for entry in existing_list:
				normalized = self._normalize_mapping_entry(entry)
				for key in geometry_keys:
					if key in normalized:
						normalized.pop(key, None)
						removed_any = True
				sanitized_entries.append(normalized)

			if not sanitized_entries:
				continue

			try:
				enriched = self._enrich_selection_geometry(
					run_id,
					model,
					sanitized_entries,
					force_refresh=force_refresh,
				)
			except Exception as exc:  # noqa: BLE001
				self.logger.warning(
					"geometry rebuild failed",
					extra={
						"run_id": run_id,
						"question_number": model.question_number,
						"error": str(exc),
					},
				)
				continue

			if enriched != model.substring_mappings or removed_any:
				model.substring_mappings = enriched

				aggregated_spans: List[str] = []
				union_rect: Optional[fitz.Rect] = None
				page_override: Optional[int] = None
				for entry in enriched:
					candidate_page = entry.get("selection_page")
					if isinstance(candidate_page, int):
						page_override = candidate_page
					bbox = entry.get("selection_bbox")
					if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
						try:
							rect = fitz.Rect(*bbox)
						except Exception:
							rect = None
						if rect is not None:
							union_rect = rect if union_rect is None else union_rect | rect
					for key in ("selection_span_ids", "span_ids"):
						span_values = entry.get(key)
						if isinstance(span_values, (list, tuple)):
							for span_id in span_values:
								if not span_id:
									continue
								text_id = str(span_id)
								if text_id not in aggregated_spans:
									aggregated_spans.append(text_id)

				if aggregated_spans or union_rect is not None or page_override is not None:
					stem_position = dict(model.stem_position or {})
					if page_override is not None:
						stem_position["page"] = int(page_override + 1)
					if union_rect is not None:
						stem_position["bbox"] = [
							float(union_rect.x0),
							float(union_rect.y0),
							float(union_rect.x1),
							float(union_rect.y1),
						]
					if aggregated_spans:
						stem_position["span_ids"] = list(aggregated_spans)
						stem_position["stem_spans"] = list(aggregated_spans)
					model.stem_position = stem_position

				db.session.add(model)
				updated += 1

		if updated:
			db.session.commit()
			try:
				self.sync_structured_mappings(run_id)
			except Exception:  # pragma: no cover - sync best effort
				self.logger.exception(
					"sync failed after geometry rebuild",
					extra={"run_id": run_id},
				)
			else:
				self.logger.info(
					"mapping geometry rebuilt",
					extra={"run_id": run_id, "questions": updated},
				)

		return updated

	def reanchor_geometry_from_rewrite(
		self,
		run_id: str,
		*,
		question_numbers: Optional[Iterable[str]] = None,
		padding: float = 1.5,
	) -> int:
		"""Reattach mapping geometry using spans detected in the rewritten PDF."""

		from ...utils.storage_paths import run_directory

		span_plan_path = run_directory(run_id) / "artifacts" / "stream_rewrite-overlay" / "span_plan.json"
		rewrite_pdf_path = run_directory(run_id) / "artifacts" / "stream_rewrite-overlay" / "after_stream_rewrite.pdf"

		if not span_plan_path.exists() or not rewrite_pdf_path.exists():
			self.logger.warning(
				"rewrite artifacts missing",
				run_id=run_id,
				span_plan=str(span_plan_path),
				rewrite_pdf=str(rewrite_pdf_path),
			)
			return 0

		structured = self.structured_manager.load(run_id)
		if not structured:
			return 0

		span_index = structured.get("pymupdf_span_index") or []
		if not span_index:
			self.logger.warning("span index missing", run_id=run_id)
			return 0

		page_map = {
			entry.get("page"): entry.get("spans") or []
			for entry in span_index
			if entry.get("page") is not None
		}

		run_pdf_path_str = structured.get("document", {}).get("source_path") or structured.get("document", {}).get("path")
		if not run_pdf_path_str:
			self.logger.warning("original pdf path missing", run_id=run_id)
			return 0

		run_pdf_path = Path(run_pdf_path_str)
		if not run_pdf_path.is_absolute():
			run_pdf_path = run_directory(run_id) / run_pdf_path
		if not run_pdf_path.exists():
			self.logger.warning("original pdf not found", run_id=run_id, pdf=str(run_pdf_path))
			return 0

		labels = None
		if question_numbers is not None:
			labels = {str(label).strip() for label in question_numbers if str(label).strip()}
			if not labels:
				return 0

		question_query = (
			QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
			.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
		)
		if labels:
			question_query = question_query.filter(QuestionManipulation.question_number.in_(labels))

		question_models = question_query.all()
		if not question_models:
			return 0

		try:
			original_doc = fitz.open(run_pdf_path)
		except Exception as exc:  # noqa: BLE001
			self.logger.warning("failed to open original pdf", run_id=run_id, error=str(exc))
			return 0

		try:
			rewrite_doc = fitz.open(rewrite_pdf_path)
		except Exception as exc:  # noqa: BLE001
			self.logger.warning("failed to open rewritten pdf", run_id=run_id, error=str(exc))
			original_doc.close()
			return 0

		span_lookup: Dict[int, Dict[str, Dict[str, Any]]] = {}
		for page_number, spans in page_map.items():
			lookup: Dict[str, Dict[str, Any]] = {}
			for span in spans:
				span_id = span.get("id")
				if not span_id:
					continue
				lookup[span_id] = span
			span_lookup[int(page_number)] = lookup

		awaiting_update = 0
		base_renderer = BaseRenderer()
		question_structured_map: Dict[str, Dict[str, Any]] = {
			str(entry.get("question_number") or entry.get("q_number")): entry
			for entry in structured.get("questions", [])
		}

		for model in question_models:
			if not model.substring_mappings:
				continue

			question_label = str(model.question_number)
			question_payload = next(
				(q for q in structured.get("questions", []) if str(q.get("question_number")) == question_label),
				{},
			)

			positioning = question_payload.get("positioning") or {}
			stem_position = model.stem_position or {}
			page_hint = positioning.get("page") or stem_position.get("page")
			page_index = 0
			if page_hint is not None:
				try:
					page_index = int(page_hint) - 1 if int(page_hint) > 0 else 0
				except (TypeError, ValueError):
					page_index = 0

			try:
				original_page = original_doc[page_index]
			except Exception:
				self.logger.warning("original page missing", run_id=run_id, question=question_label)
				continue

			try:
				rewrite_page = rewrite_doc[page_index]
			except Exception:
				self.logger.warning("rewrite page missing", run_id=run_id, question=question_label)
				continue

			question_block = self._locate_question_block(original_page, question_label)
			question_bbox = fitz.Rect(question_block) if question_block else None

			span_list = span_lookup.get(page_index + 1, {})

			updated_any = False
			for mapping in model.substring_mappings:
				replacement = base_renderer.strip_zero_width(str(mapping.get("replacement") or "")).strip()
				if not replacement:
					continue

				candidate_rects = rewrite_page.search_for(replacement)
				if not candidate_rects:
					self.logger.warning(
						"replacement not found in rewritten pdf",
						run_id=run_id,
						question=question_label,
						replacement=replacement,
					)
					continue

				selected_rect = None
				if question_bbox is not None:
					for rect in candidate_rects:
						if fitz.Rect(rect).intersects(question_bbox):
							selected_rect = fitz.Rect(rect)
							break
				if selected_rect is None:
					selected_rect = fitz.Rect(candidate_rects[0])

				selected_rect.x0 -= padding
				selected_rect.x1 += padding
				selected_rect.y0 -= padding
				selected_rect.y1 += padding
				selected_rect &= rewrite_page.rect

				span_ids = self._collect_span_ids_for_rect(span_list, selected_rect)
				if not span_ids:
					span_ids = mapping.get("selection_span_ids") or []

				quad = [
					float(selected_rect.x0),
					float(selected_rect.y0),
					float(selected_rect.x1),
					float(selected_rect.y0),
					float(selected_rect.x1),
					float(selected_rect.y1),
					float(selected_rect.x0),
					float(selected_rect.y1),
				]
				bbox_list = [float(selected_rect.x0), float(selected_rect.y0), float(selected_rect.x1), float(selected_rect.y1)]
				self.logger.info(
					"rewrite search anchor",
					run_id=run_id,
					question=question_label,
					replacement=replacement,
					bbox=bbox_list,
				)

				mapping["selection_page"] = page_index
				mapping["selection_bbox"] = bbox_list
				mapping["selection_quads"] = [quad]
				mapping["selection_span_ids"] = span_ids
				mapping["span_ids"] = span_ids
				mapping["geometry_source"] = "rewrite_search"
				updated_any = True

			if updated_any:
				all_span_ids = []
				for entry in model.substring_mappings:
					all_span_ids.extend(entry.get("selection_span_ids", []))
				model.stem_position = {
					"page": page_index + 1,
					"bbox": [
						float(question_bbox.x0),
						float(question_bbox.y0),
						float(question_bbox.x1),
						float(question_bbox.y1),
					] if question_bbox else bbox_list,
					"span_ids": list(dict.fromkeys(all_span_ids)),
					"stem_spans": list(dict.fromkeys(all_span_ids)),
				}
				payload_json = json.loads(json.dumps(model.substring_mappings))
				db.session.execute(
					text(
						"UPDATE question_manipulations SET substring_mappings = :mappings, stem_position = :stem WHERE id = :id"
					),
					{
						"mappings": json.dumps(payload_json),
						"stem": json.dumps(model.stem_position),
						"id": model.id,
					},
				)
				structured_entry = question_structured_map.get(question_label)
				if structured_entry is not None:
					manip = structured_entry.setdefault("manipulation", {})
					manip["substring_mappings"] = payload_json
					structured_entry["manipulation"] = manip
					structured_entry["stem_position"] = model.stem_position
				awaiting_update += 1
				self.logger.info(
					"geometry reanchored from rewrite",
					run_id=run_id,
					question=question_label,
					mappings=len(model.substring_mappings),
				)

		original_doc.close()
		rewrite_doc.close()

		if awaiting_update:
			db.session.commit()
			self.structured_manager.save(run_id, structured)

		return awaiting_update

	def _collect_span_ids_for_rect(
		self,
		span_lookup: Dict[str, Dict[str, Any]],
		target_rect: fitz.Rect,
	) -> List[str]:
		if not span_lookup:
			return []

		collected: List[str] = []
		for span_id, span in span_lookup.items():
			bbox = span.get("bbox")
			if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
				continue
			try:
				span_rect = fitz.Rect(*bbox)
			except Exception:
				continue
			if span_rect.intersects(target_rect):
				collected.append(span_id)

		return collected

	def _locate_question_block(self, page: fitz.Page, q_number: str) -> Optional[Tuple[float, float, float, float]]:
		prefix = f"{q_number}."
		for block in page.get_text("blocks"):
			if not block or len(block) < 5:
				continue
			x0, y0, x1, y1, text, *_ = block
			if text and text.strip().startswith(prefix):
				return (x0, y0, x1, y1)
		return None

	def _extract_model_content(self, model_result: Dict[str, Any]) -> str:
		raw = model_result.get("raw_response") if isinstance(model_result, dict) else None
		if isinstance(raw, dict):
			choices = raw.get("choices") or []
			if choices:
				message = choices[0].get("message", {}) or {}
				content = message.get("content")
				if isinstance(content, str):
					return content.strip()
				if isinstance(content, list):
					parts: List[str] = []
					for part in content:
						if isinstance(part, dict):
							text = part.get("text") or part.get("content") or ""
							parts.append(str(text))
						else:
							parts.append(str(part))
					joined = "".join(parts).strip()
					if joined:
						return joined
		content = model_result.get("response") if isinstance(model_result, dict) else None
		if isinstance(content, str):
			return content.strip()
		return ""

	def _ranges_overlap(self, a: Tuple[int, int], b: Tuple[int, int]) -> bool:
		return max(a[0], b[0]) < min(a[1], b[1])

	def _extract_option_letter(self, value: Optional[Any]) -> Optional[str]:
		"""Return the leading option letter (A-D, etc.) if present."""
		if value is None:
			return None
		text = str(value).strip()
		if not text:
			return None
		match = re.match(r"([A-Za-z])", text)
		if not match:
			match = re.search(r"([A-Za-z])", text)
		if not match:
			return None
		return match.group(1).upper()

	def _infer_indices(
		self,
		original: str,
		text: str,
		used_ranges: List[Tuple[int, int]],
	) -> Optional[Tuple[int, int]]:
		if not original:
			return None
		length = len(original)
		if length == 0:
			return None

		cursor = 0
		text_lower = text.lower()
		needle_lower = original.lower()
		while cursor <= len(text) - length:
			pos = text.find(original, cursor)
			case_adjusted = False
			if pos == -1:
				pos = text_lower.find(needle_lower, cursor)
				case_adjusted = pos != -1
			if pos == -1:
				break
			candidate = (pos, pos + length)
			cursor = pos + 1
			if any(self._ranges_overlap(candidate, existing) for existing in used_ranges):
				continue
			if case_adjusted:
				extracted = text[candidate[0] : candidate[1]]
				return candidate[0], candidate[0] + len(extracted)
			return candidate
		return None

	def _normalize_ai_mappings(
		self,
		stem_text: str,
		mappings_payload: List[Dict[str, Any]],
	) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
		normalized_entries: List[Dict[str, Any]] = []
		used_ranges: List[Tuple[int, int]] = []
		inferred_ranges: List[Dict[str, Any]] = []
		skipped_entries: List[Dict[str, Any]] = []

		for idx, entry in enumerate(mappings_payload):
			if not isinstance(entry, dict):
				continue
			norm = self._normalize_mapping_entry(entry)
			norm.setdefault("context", "question_stem")
			norm.setdefault("id", uuid.uuid4().hex[:10])
			start_pos = norm.get("start_pos")
			end_pos = norm.get("end_pos")
			valid_range = (
				isinstance(start_pos, int)
				and isinstance(end_pos, int)
				and start_pos is not None
				and end_pos is not None
				and end_pos > start_pos
				and start_pos >= 0
				and end_pos <= len(stem_text)
			)

			if valid_range and not any(self._ranges_overlap((start_pos, end_pos), existing) for existing in used_ranges):
				normalized_entries.append(norm)
				used_ranges.append((start_pos, end_pos))
				continue

			fallback_range = self._infer_indices(str(norm.get("original") or ""), stem_text, used_ranges)
			if fallback_range:
				norm["start_pos"], norm["end_pos"] = fallback_range
				extracted = stem_text[fallback_range[0] : fallback_range[1]]
				if extracted and extracted != norm.get("original"):
					norm["original"] = extracted
				normalized_entries.append(norm)
				used_ranges.append(fallback_range)
				inferred_ranges.append(
					{
						"index": idx,
						"original": norm.get("original"),
						"replacement": norm.get("replacement"),
						"start_pos": fallback_range[0],
						"end_pos": fallback_range[1],
					}
				)
				continue

			skipped_entries.append(
				{
					"index": idx,
					"original": norm.get("original"),
					"replacement": norm.get("replacement"),
					"reason": "missing_or_invalid_indices",
				}
			)

		return normalized_entries, inferred_ranges, skipped_entries

	def _collect_safe_span_candidates(
		self,
		structured_data: Dict[str, Any],
		page_index: int,
		stem_bbox: Optional[List[float]],
		keywords: Optional[List[str]] = None,
		limit: int = 80,
	) -> List[Dict[str, str]]:
		pdf_meta = structured_data.get("document") or {}
		pdf_path = pdf_meta.get("source_path")
		if not pdf_path:
			return []

		try:
			doc = fitz.open(pdf_path)
		except Exception:
			return []

		try:
			if len(doc) == 0:
				return []
			clamped_page = max(0, min(int(page_index or 0), len(doc) - 1))
			page = doc[clamped_page]
			records = collect_span_records(page, clamped_page)
		finally:
			try:
				doc.close()
			except Exception:
				pass

		expanded_rect: Optional[fitz.Rect] = None
		if stem_bbox and len(stem_bbox) == 4:
			try:
				base_rect = fitz.Rect(*[float(v) for v in stem_bbox])
				expanded_rect = fitz.Rect(base_rect)
				expanded_rect.x0 -= 25
				expanded_rect.y0 -= 30
				expanded_rect.x1 += 25
				expanded_rect.y1 += 30
			except Exception:
				expanded_rect = None

		filtered_records: List[SpanRecord] = []
		for record in records:
			record_rect = fitz.Rect(*record.bbox)
			if expanded_rect is not None and not record_rect.intersects(expanded_rect):
				continue
			filtered_records.append(record)

		filtered_records.sort(key=lambda r: (r.block_index, r.line_index, r.span_index))

		single_entries: List[Dict[str, str]] = []
		combo_entries: List[Dict[str, str]] = []
		seen_texts: set[str] = set()
		keywords_lower = [kw.lower() for kw in (keywords or []) if kw]

		for record in filtered_records:
			text_raw = (record.text or "").replace("\n", "").strip()
			normalized = (record.normalized_text or "").replace("\n", "").strip()
			if not text_raw and normalized:
				text_raw = normalized
			if not text_raw and not normalized:
				continue
			if keywords_lower:
				text_lower = text_raw.lower()
				norm_lower = normalized.lower()
				if not any(kw in text_lower or kw in norm_lower for kw in keywords_lower):
					continue
			fingerprint = text_raw or normalized
			if not fingerprint or fingerprint in seen_texts:
				continue
			span_id = (
				f"page{record.page_index}:block{record.block_index}:line{record.line_index}:span{record.span_index}"
			)
			single_entries.append(
				{
					"span_id": span_id,
					"text": text_raw,
					"normalized": normalized,
				}
			)
			seen_texts.add(fingerprint)

		from collections import defaultdict
		lines: Dict[Tuple[int, int], List[SpanRecord]] = defaultdict(list)
		for record in filtered_records:
			lines[(record.block_index, record.line_index)].append(record)

		for (block_idx, line_idx), span_list in lines.items():
			span_list.sort(key=lambda r: r.span_index)
			combined_raw = "".join((span.text or "").replace("\n", "") for span in span_list).strip()
			combined_norm = "".join((span.normalized_text or "").replace("\n", "") for span in span_list).strip()
			if combined_raw or combined_norm:
				fingerprint = combined_raw or combined_norm
				match_ok = True
				if keywords_lower:
					combined_lower = fingerprint.lower()
					match_ok = any(kw in combined_lower for kw in keywords_lower)
				if fingerprint and fingerprint not in seen_texts and match_ok:
					span_id = (
						f"page{span_list[0].page_index}:block{block_idx}:line{line_idx}:span{span_list[0].span_index}-span{span_list[-1].span_index}"
					)
					combo_entries.append(
						{
							"span_id": span_id,
							"text": combined_raw,
							"normalized": combined_norm,
						}
					)
					seen_texts.add(fingerprint)

			window_limit = min(4, len(span_list))
			for window in range(2, window_limit + 1):
				for i in range(len(span_list) - window + 1):
					subset = span_list[i : i + window]
					combined_raw = "".join((span.text or "").replace("\n", "") for span in subset).strip()
					combined_norm = "".join((span.normalized_text or "").replace("\n", "") for span in subset).strip()
					fingerprint = combined_raw or combined_norm
					if not fingerprint or fingerprint in seen_texts:
						continue
					match_ok = True
					if keywords_lower:
						combined_lower = fingerprint.lower()
						match_ok = any(kw in combined_lower for kw in keywords_lower)
					if not match_ok:
						continue
					span_id = (
						f"page{subset[0].page_index}:block{block_idx}:line{line_idx}:span{subset[0].span_index}-span{subset[-1].span_index}"
					)
					combo_entries.append(
						{
							"span_id": span_id,
							"text": combined_raw,
							"normalized": combined_norm,
						}
					)
					seen_texts.add(fingerprint)

		return (single_entries + combo_entries)[:limit]

	def _build_text_span_candidates(
		self,
		stem_text: str,
		limit: int = 80,
		max_window: int = 1,
	) -> List[Dict[str, str]]:
		if not stem_text:
			return []

		# Identify token boundaries while preserving original spacing
		tokens = list(re.finditer(r"\S+", stem_text))
		if not tokens:
			return []

		def _is_acceptable(value: str) -> bool:
			s = value.strip()
			if len(s) < 4:
				return False
			# Require start and end characters to be alphabetic to avoid punctuation fragments
			if not (s[0].isalpha() and s[-1].isalpha()):
				return False
			# Skip strings with digits or typical equation symbols/parentheses
			if re.search(r"[0-9()\[\]{}<>/=+*^]", s):
				return False
			# Ignore very common filler words that rarely make good substitutions
			stopwords = {
				"the",
				"and",
				"with",
				"from",
				"that",
				"this",
				"which",
				"might",
				"could",
				"should",
				"would",
				"is",
				"are",
				"be",
				"have",
				"has",
				"had",
			}
			if s.lower() in stopwords:
				return False
			# Limit very long sequences to avoid overwhelming the model
			if len(s) > 60:
				return False
			return True

		recorded: List[Dict[str, str]] = []
		seen: set[str] = set()

		for window in range(1, max_window + 1):
			for idx in range(len(tokens) - window + 1):
				start = tokens[idx].start()
				end = tokens[idx + window - 1].end()
				substring = stem_text[start:end]
				normalized = substring.strip()
				if not normalized:
					continue
				if not _is_acceptable(normalized):
					continue
				fingerprint = normalized.lower()
				if fingerprint in seen:
					continue
				seen.add(fingerprint)
				recorded.append(
					{
						"span_id": f"stem:{start}:{end}",
						"text": normalized,
						"normalized": normalized,
					}
				)
				if len(recorded) >= limit:
					return recorded
		return recorded

	def _invoke_generation_call(
		self,
		*,
		payload: Dict[str, Any],
		provider: str,
		strategy_definition: StrategyDefinition,
		stem_text: str,
		question_type: str,
		run_id: str,
		question_model: QuestionManipulation,
	) -> GenerationCallResult:
		fallback_used = False
		strategy_used: Optional[str] = None
		result: Dict[str, Any] = {}
		raw_response: Optional[Dict[str, Any]] = None
		raw_content = ""
		parsed_payload: Dict[str, Any] = {}
		mappings_payload: List[Dict[str, Any]] = []

		try:
			result = self.ai_client.call_model(provider=provider, payload=payload)
		except Exception as exc:  # noqa: BLE001
			self.logger.error(
				"auto_generate call failed",
				run_id=run_id,
				question_id=question_model.id,
				provider=provider,
				error=str(exc),
				exc_info=True,
			)
			fallback_mappings, heuristic_strategy = generate_heuristic_mappings(
				stem_text,
				question_type,
				strategy_definition,
			)
			if not fallback_mappings:
				raise
			fallback_used = True
			strategy_used = heuristic_strategy
			parsed_payload = {
				"mappings": fallback_mappings,
				"fallback": True,
				"reason": "call_failure",
				"error": str(exc),
			}
			raw_content = json.dumps(parsed_payload)
			mappings_payload = fallback_mappings
		else:
			raw_response = result.get("raw_response") if isinstance(result, dict) else None
			raw_content = self._extract_model_content(result)
			if raw_content:
				try:
					parsed_payload = json.loads(raw_content)
				except json.JSONDecodeError as exc:
					self.logger.warning(
						"auto_generate JSON decode failure",
						run_id=run_id,
						question_id=question_model.id,
						provider=provider,
						error=str(exc),
					)
					parsed_payload = {}
			mappings_payload = parsed_payload.get("mappings") if isinstance(parsed_payload, dict) else None
			if isinstance(parsed_payload, dict):
				strategy_used = parsed_payload.get("strategy")

		if not fallback_used:
			if not isinstance(mappings_payload, list) or not mappings_payload:
				fallback_mappings, heuristic_strategy = generate_heuristic_mappings(
					stem_text,
					question_type,
					strategy_definition,
				)
				if not fallback_mappings:
					raise ValueError("Model response did not contain mappings")
				parsed_payload = {
					"mappings": fallback_mappings,
					"fallback": True,
					"reason": "empty_response",
				}
				raw_content = raw_content or json.dumps(parsed_payload)
				mappings_payload = fallback_mappings
				strategy_used = heuristic_strategy
				fallback_used = True
			else:
				strategy_used = strategy_used or strategy_definition.key
		else:
			if not isinstance(parsed_payload, dict):
				parsed_payload = {"mappings": mappings_payload or []}
			parsed_payload.setdefault("fallback", True)
			parsed_payload.setdefault("reason", "call_failure")
			if strategy_used:
				parsed_payload.setdefault("strategy", strategy_used)
			else:
				strategy_used = strategy_definition.key
				raw_content = raw_content or json.dumps(parsed_payload)

		provider_used = (
			result.get("provider")
			if isinstance(result, dict) and result.get("provider")
			else provider
		)

		return GenerationCallResult(
			result=result if isinstance(result, dict) else {},
			raw_response=raw_response if isinstance(raw_response, dict) else None,
			raw_content=raw_content,
			parsed_payload=parsed_payload if isinstance(parsed_payload, dict) else {},
			mappings_payload=list(mappings_payload or []),
			fallback_used=fallback_used,
			strategy_used=strategy_used,
			provider_used=provider_used,
		)

	def _augment_prompt_with_feedback(
		self,
		base_prompt: str,
		feedback_notes: List[str],
		avoid_substrings: Optional[set[str]] = None,
		require_option_change: bool = False,
		gold_answer: Optional[str] = None,
	) -> str:
		if not feedback_notes and not avoid_substrings and not require_option_change:
			return base_prompt
		recent_notes = feedback_notes[-3:]
		sections: List[str] = []
		if recent_notes:
			diagnostics = "\n".join(f"- {note}" for note in recent_notes if note)
			if diagnostics:
				sections.append("Previous attempt diagnostics:\n" + diagnostics)
		if avoid_substrings:
			avoid_list = sorted(avoid_substrings)
			if avoid_list:
				preview = ", ".join(avoid_list[:5])
				sections.append(f"Avoid reusing these substrings: {preview}.")
		if require_option_change and gold_answer:
			sections.append(
				f"Ensure the new mapping alters the question so the answer letter changes from option {gold_answer}."
			)
		if not sections:
			return base_prompt
		return f"{base_prompt}\n\n" + "\n".join(sections)

	def _build_feedback_note(self, mapping: Dict[str, Any], reason: str) -> str:
		original = str(mapping.get("original") or "").strip()
		replacement = str(mapping.get("replacement") or "").strip()
		reason_clean = (reason or "Validation failed").strip()
		if len(reason_clean) > 200:
			reason_clean = reason_clean[:197] + "…"
		return f"Replacement '{original}' → '{replacement}' was rejected because {reason_clean}"

	def _validate_candidate_mapping(
		self,
		*,
		run_id: str,
		question_model: QuestionManipulation,
		mapping: Dict[str, Any],
		stem_text: str,
		strategy_key: str,
		strategy_validation_focus: str,
		provider: str,
	) -> Tuple[Dict[str, Any], Dict[str, Any], ValidationResult, str]:
		question_type = question_model.question_type or "mcq_single"
		uses_signal_strategy = question_type in SIGNAL_STRATEGY_TYPES
		uses_target_strategy = (
			question_type in TARGET_STRATEGY_TYPES or not uses_signal_strategy
		)

		normalized_mapping = self._normalize_mapping_entry(mapping)
		expected_target_letter: Optional[str] = None
		expected_target_text: Optional[str] = None
		missing_target_metadata = False

		if uses_target_strategy:
			expected_target_letter = self._extract_option_letter(normalized_mapping.get("target_option"))
			if expected_target_letter:
				expected_target_text = normalized_mapping.get("target_option_text")
				if not expected_target_text:
					expected_target_text = self._resolve_option_text(question_model, expected_target_letter)
				if expected_target_text:
					normalized_mapping["target_option_text"] = expected_target_text
				normalized_mapping["target_option"] = expected_target_letter
			else:
				missing_target_metadata = True
				normalized_mapping.pop("target_option", None)
				normalized_mapping.pop("target_option_text", None)

		signal_metadata: Optional[Dict[str, str]] = None
		if uses_signal_strategy:
			signal_metadata = self._sanitize_signal_metadata(normalized_mapping)
			if signal_metadata:
				normalized_mapping.update(signal_metadata)
			else:
				for key in ("signal_type", "signal_phrase", "signal_notes"):
					normalized_mapping.pop(key, None)

		ordered_entries = [normalized_mapping]
		modified_question = self.substrings.apply_mappings_to_text(stem_text, ordered_entries)

		# Use optimized GPT-5.1 validation that answers and validates in one call
		# This eliminates the need for the separate gpt-4o call
		options_data = question_model.options_data if isinstance(question_model.options_data, dict) else None
		validator = GPT5ValidationService()
		
		# Use GPT-5.1 to answer the manipulated question and validate in one call
		if validator.is_configured():
			import asyncio
			validation_result = asyncio.run(validator.validate_answer_deviation(
				question_text=stem_text,
				question_type=question_type,
				gold_answer=question_model.gold_answer or "",
				test_answer=None,  # Let GPT-5.1 generate it from manipulated question
				manipulated_question_text=modified_question,  # Pass manipulated question
				options_data=options_data,
				target_option=expected_target_letter if uses_target_strategy else None,
				target_option_text=expected_target_text if uses_target_strategy else None,
				signal_metadata=signal_metadata if uses_signal_strategy else None,
				run_id=run_id,
			))
			# Extract test_answer from validation result
			test_answer = validation_result.test_answer or ""
		else:
			# Fallback to offline heuristic if GPT-5.1 not configured
			test_answer = ""
			deviation = 0.8 if (question_model.gold_answer or "").strip().lower() != test_answer.strip().lower() else 0.2
			confidence = 0.65 if deviation >= 0.5 else 0.3
			validation_result = ValidationResult(
				is_valid=deviation >= 0.5,
				confidence=confidence,
				deviation_score=deviation,
				reasoning="Offline heuristic validation (no GPT-5 configuration)",
				semantic_similarity=1.0 - deviation,
				factual_accuracy=False,
				question_type_specific_notes=strategy_validation_focus,
				gold_answer=question_model.gold_answer or "",
				test_answer=test_answer,
				model_used="offline-heuristic",
			)

		test_option_letter = self._extract_option_letter(test_answer)
		gold_option_letter = self._extract_option_letter(question_model.gold_answer)
		target_matched: Optional[bool] = None
		signal_detected: Optional[bool] = None
		option_change_failed = False
		failure_reason = ""

		if uses_target_strategy:
			if missing_target_metadata:
				option_change_failed = True
				failure_reason = "Target-based question requires a target_option."
			elif not test_option_letter:
				option_change_failed = True
				failure_reason = "Model response did not include a recognizable option letter."
			elif gold_option_letter and test_option_letter == gold_option_letter:
				option_change_failed = True
				failure_reason = "Model still selected the gold option."
			elif expected_target_letter and test_option_letter != expected_target_letter:
				option_change_failed = True
				failure_reason = f"Model selected {test_option_letter or '?'} instead of target {expected_target_letter}."
			target_matched = (
				expected_target_letter is not None and test_option_letter == expected_target_letter
			)
		elif uses_signal_strategy and signal_metadata:
			signal_detected = self._detect_signal_in_answer(signal_metadata, test_answer)

		if uses_signal_strategy and signal_metadata and signal_detected is None:
			signal_detected = False

		threshold = validator.get_validation_threshold(question_type) if hasattr(validator, "get_validation_threshold") else 0.0

		if uses_target_strategy and option_change_failed:
			validation_result.is_valid = False
			validation_result.confidence = min(validation_result.confidence, 0.2)
			validation_result.deviation_score = min(validation_result.deviation_score, 0.2)
			validation_result.reasoning = failure_reason or validation_result.reasoning

		validation_result.target_matched = target_matched
		validation_result.signal_detected = signal_detected
		diagnostics_payload = {
			"target_option": expected_target_letter,
			"target_option_text": expected_target_text,
			"target_matched": target_matched,
			"signal_detected": signal_detected,
			"signal_phrase": (signal_metadata or {}).get("signal_phrase") if signal_metadata else None,
			"signal_type": (signal_metadata or {}).get("signal_type") if signal_metadata else None,
			"failure_reason": failure_reason if option_change_failed else None,
			"test_option": test_option_letter,
		}
		validation_result.diagnostics = {
			key: value for key, value in diagnostics_payload.items() if value is not None
		}

		diagnostics_snapshot = dict(validation_result.diagnostics) if validation_result.diagnostics else {}
		validation_record = {
			"model": "gpt-5.1" if validator.is_configured() else "offline",
			"response": test_answer,
			"gold": question_model.gold_answer,
			"prompt_len": len(modified_question),
			"strategy": strategy_key,
			"strategy_focus": strategy_validation_focus,
			"gpt5_validation": {
				"is_valid": validation_result.is_valid,
				"confidence": validation_result.confidence,
				"deviation_score": validation_result.deviation_score,
				"reasoning": validation_result.reasoning,
				"semantic_similarity": validation_result.semantic_similarity,
				"factual_accuracy": validation_result.factual_accuracy,
				"question_type_notes": validation_result.question_type_specific_notes,
				"model_used": validation_result.model_used,
				"threshold": threshold,
			},
			"diagnostics": diagnostics_snapshot,
			"option_change_failed": option_change_failed,
		}

		augmented_mapping = dict(mapping)
		augmented_mapping.update(
			{
				"validated": validation_result.is_valid,
				"confidence": validation_result.confidence,
				"deviation_score": validation_result.deviation_score,
				"validation": validation_record,
				"validation_diagnostics": validation_record.get("diagnostics"),
				"auto_generated": True,
				"generated_by": provider,
				"test_answer": test_answer,
				"validation_model": validation_result.model_used,
			}
		)
		augmented_mapping["option_change_failed"] = option_change_failed

		if expected_target_letter:
			augmented_mapping["target_option"] = expected_target_letter
			if expected_target_text:
				augmented_mapping["target_option_text"] = expected_target_text
		else:
			augmented_mapping.pop("target_option", None)
			augmented_mapping.pop("target_option_text", None)
		if test_option_letter:
			augmented_mapping["test_option"] = test_option_letter
		else:
			augmented_mapping.pop("test_option", None)
		if signal_metadata:
			augmented_mapping.update(signal_metadata)

		return augmented_mapping, validation_record, validation_result, test_answer

	async def auto_generate_all_questions(self, run_id: str) -> Dict[str, Any]:
		"""Automatically generate mappings for all questions using streamlined service."""
		from ...services.mapping.streamlined_mapping_service import StreamlinedMappingService
		
		service = StreamlinedMappingService()
		result = await service.generate_mappings_for_all_questions(run_id)
		
		self.logger.info(
			"Auto-generation completed",
			run_id=run_id,
			success_count=result.get("success_count", 0),
			failed_count=result.get("failed_count", 0),
		)
		
		return result

	def auto_generate_for_question(
		self,
		*,
		run_id: str,
		question_model: QuestionManipulation,
		provider: str = "openai:gpt-5.1",
		structured: Optional[Dict[str, Any]] = None,
		max_completion_tokens: int = 4000,
		force_refresh: bool = False,
	) -> AutoMappingOutcome:
		return _auto_generate_for_question_impl(
			service=self,
			run_id=run_id,
			question_model=question_model,
			provider=provider,
			structured=structured,
			max_completion_tokens=max_completion_tokens,
			force_refresh=force_refresh,
		)

	async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
		strategy = config.get("mapping_strategy", "unicode_steganography")
		result = await asyncio.to_thread(self._apply_mappings, run_id, strategy)

		# Automatically generate mappings for all questions during pipeline execution
		self.logger.info("Auto-generating mappings for all questions", run_id=run_id)
		generation_result = await self.auto_generate_all_questions(run_id)
		result["auto_generation"] = generation_result

		return result

	def _apply_mappings(self, run_id: str, strategy: str) -> Dict[str, Any]:
		structured = self.structured_manager.load(run_id)
		questions_data = structured.setdefault("questions", [])
		questions_models = (
			QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
			.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
			.all()
		)

		# Ensure we have a stable mapping between DB records and structured entries
		structured_by_qnum = {}
		for entry in questions_data:
			label = str(entry.get("q_number") or entry.get("question_number") or "").strip()
			if label:
				structured_by_qnum[label] = entry

		def ensure_structured_entry(model: QuestionManipulation) -> Dict[str, Any]:
			label = str(model.question_number).strip()
			if label in structured_by_qnum:
				return structured_by_qnum[label]
			node: Dict[str, Any] = {
				"q_number": label,
				"question_number": label,
			}
			questions_data.append(node)
			structured_by_qnum[label] = node
			return node

		# Character map is still produced, but we no longer auto-generate word-level mappings here
		mapping_result = self.mapper.create_mapping(strategy)

		total_effectiveness = 0.0
		mappings_created = 0
		auto_generated_count = 0

		# Compute true gold answers per question up-front (skip if already populated)
		for question_model in questions_models:
			question_dict = ensure_structured_entry(question_model)
			if question_model.gold_answer:
				question_dict["gold_answer"] = question_model.gold_answer
				question_dict["gold_confidence"] = question_model.gold_confidence
				continue
			gold_answer, gold_conf = self._compute_true_gold(question_model)
			question_model.gold_answer = gold_answer
			question_model.gold_confidence = gold_conf
			question_dict["gold_answer"] = gold_answer
			question_dict["gold_confidence"] = gold_conf
			db.session.add(question_model)

		db.session.commit()

		# Initialize manipulation metadata but do not prefill substring_mappings; UI will drive them
		for question_model in questions_models:
			question_dict = ensure_structured_entry(question_model)
			question_model.manipulation_method = question_model.manipulation_method or "smart_substitution"
			self._merge_question_payload(question_dict, question_model)
			normalized_mappings = [
				self._normalize_mapping_entry(entry)
				for entry in list(question_model.substring_mappings or [])
			]
			if normalized_mappings:
				question_model.substring_mappings = normalized_mappings
			manipulation_payload = {
				"method": question_model.manipulation_method,
				"substring_mappings": normalized_mappings,
				"effectiveness_score": question_model.effectiveness_score,
				"character_strategy": mapping_result.strategy,
			}
			if normalized_mappings:
				manipulation_payload["auto_generate_status"] = "prefilled"
			else:
				manipulation_payload["auto_generate_status"] = "pending"
			question_dict["manipulation"] = manipulation_payload
			db.session.add(question_model)

		db.session.commit()

		structured["global_mappings"] = {
			"character_strategy": mapping_result.strategy,
			"mapping_dictionary": mapping_result.character_map,
			"effectiveness_stats": {
				"total_questions": len(questions_models),
				"average_effectiveness": (total_effectiveness / len(questions_models)) if questions_models else 0,
				"total_characters_mapped": len(mapping_result.character_map),
				"coverage_percentage": round(mapping_result.coverage * 100, 2),
			},
		}

		metadata = structured.setdefault("pipeline_metadata", {})
		stages_completed = set(metadata.get("stages_completed", []))
		stages_completed.add("smart_substitution")
		metadata.update(
			{
				"current_stage": "smart_substitution",
				"stages_completed": list(stages_completed),
				"last_updated": isoformat(utc_now()),
			}
		)
		self.structured_manager.save(run_id, structured)

		# Persist a CharacterMapping record for reference
		mapping_record = CharacterMapping(
			pipeline_run_id=run_id,
			mapping_strategy=mapping_result.strategy,
			character_map=mapping_result.character_map,
		)
		db.session.add(mapping_record)
		db.session.commit()

		return {
			"questions_processed": len(questions_models),
			"total_substitutions": mappings_created,
			"average_effectiveness": (total_effectiveness / len(questions_models)) if questions_models else 0,
			"auto_generated_questions": auto_generated_count,
		}

	def _generate_question_mappings(self, question: Dict[str, Any], mapping_result: MappingResult) -> List[Dict]:
		# Deprecated: UI-driven mappings now. Keep method for potential future automation.
		return []

	def _merge_question_payload(self, question_dict: Dict[str, Any], question_model: QuestionManipulation) -> None:
		"""Ensure structured question entry mirrors the database payload for deterministic renders."""
		question_dict["manipulation_id"] = question_model.id
		question_dict["sequence_index"] = question_model.sequence_index
		if question_model.source_identifier:
			question_dict["source_identifier"] = question_model.source_identifier

		number = str(question_model.question_number).strip()
		if number:
			question_dict.setdefault("q_number", number)
			question_dict.setdefault("question_number", number)

		if question_model.question_type:
			question_dict["question_type"] = question_model.question_type

		if question_model.original_text:
			question_dict["original_text"] = question_model.original_text

		stem_text = question_dict.get("stem_text") or question_model.original_text
		if stem_text:
			question_dict["stem_text"] = stem_text

		if question_model.options_data:
			question_dict["options"] = question_model.options_data

		if question_model.stem_position:
			question_dict["stem_position"] = question_model.stem_position
			positioning = dict(question_dict.get("positioning") or {})
			page = positioning.get("page") or question_model.stem_position.get("page")
			bbox = positioning.get("bbox") or question_model.stem_position.get("bbox")
			selection_page_override = None
			for entry in list(question_model.substring_mappings or []):
				candidate = self._normalize_mapping_entry(entry).get("selection_page")
				if isinstance(candidate, int):
					selection_page_override = candidate
					break
			if selection_page_override is not None:
				page = selection_page_override
			if page is not None:
				positioning["page"] = page
			if bbox is not None:
				positioning["bbox"] = bbox
			if positioning:
				question_dict["positioning"] = positioning

		# Preserve substring mappings and metadata if already provided
		manipulation = dict(question_dict.get("manipulation") or {})
		if question_model.substring_mappings is not None and not manipulation.get("substring_mappings"):
			manipulation["substring_mappings"] = [
				self._normalize_mapping_entry(entry) for entry in list(question_model.substring_mappings or [])
			]
		if question_model.effectiveness_score is not None:
			manipulation.setdefault("effectiveness_score", question_model.effectiveness_score)
		if manipulation:
			question_dict["manipulation"] = manipulation

	def _sanitize_glyph_path(self, glyph_path: Dict[str, Any]) -> Dict[str, int]:
		"""Normalize glyph path metadata to integer indices."""
		if not isinstance(glyph_path, dict):
			return {}

		keys = ("block", "line", "span", "char_start", "char_end")
		sanitized: Dict[str, int] = {}
		for key in keys:
			value = glyph_path.get(key)
			if value is None:
				continue
			try:
				sanitized[key] = int(value)
			except (TypeError, ValueError):
				continue

		start = sanitized.get("char_start")
		end = sanitized.get("char_end")
		if start is not None and end is not None and end < start:
			sanitized.pop("char_start", None)
			sanitized.pop("char_end", None)

		return sanitized

	def _normalize_mapping_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
		"""Ensure mapping payload is JSON-safe and includes selection geometry if provided."""
		normalized = dict(entry or {})
		if not normalized.get("id"):
			normalized["id"] = uuid.uuid4().hex[:10]
		normalized.setdefault("context", "question_stem")
		if "start_pos" in normalized:
			try:
				normalized["start_pos"] = int(normalized.get("start_pos"))
			except (TypeError, ValueError):
				normalized["start_pos"] = None
		if "end_pos" in normalized:
			try:
				normalized["end_pos"] = int(normalized.get("end_pos"))
			except (TypeError, ValueError):
				normalized["end_pos"] = None

		selection_page = normalized.get("selection_page")
		if selection_page is not None:
			try:
				normalized["selection_page"] = int(selection_page)
			except (TypeError, ValueError):
				normalized["selection_page"] = selection_page

		selection_bbox = normalized.get("selection_bbox")
		if isinstance(selection_bbox, (list, tuple)) and len(selection_bbox) == 4:
			try:
				normalized["selection_bbox"] = [float(v) for v in selection_bbox]
			except (TypeError, ValueError):
				normalized["selection_bbox"] = selection_bbox

		selection_quads = normalized.get("selection_quads") or []
		if isinstance(selection_quads, (list, tuple)):
			quads: List[List[float]] = []
			for quad in selection_quads:
				if isinstance(quad, (list, tuple)) and len(quad) == 8:
					try:
						quads.append([float(v) for v in quad])
					except (TypeError, ValueError):
						continue
			if quads:
				normalized["selection_quads"] = quads

		glyph_path = normalized.get("matched_glyph_path") or normalized.get("selection_glyph_path")
		if isinstance(glyph_path, dict):
			sanitized = self._sanitize_glyph_path(glyph_path)
			if sanitized:
				normalized["matched_glyph_path"] = sanitized
				if "selection_glyph_path" in normalized:
					normalized["selection_glyph_path"] = sanitized
			else:
				normalized.pop("matched_glyph_path", None)
				normalized.pop("selection_glyph_path", None)

		target_option = normalized.get("target_option")
		if target_option is not None:
			letter = self._extract_option_letter(target_option)
			if letter:
				normalized["target_option"] = letter
			else:
				normalized.pop("target_option", None)

		return normalized

	def _canonicalize_mappings_for_compare(
		self,
		mappings: Iterable[Dict[str, Any]],
	) -> List[Dict[str, Any]]:
		canonical: List[Dict[str, Any]] = []
		for entry in mappings or []:
			norm = self._normalize_mapping_entry(entry)
			start_pos = norm.get("start_pos")
			end_pos = norm.get("end_pos")
			if start_pos is None or end_pos is None:
				continue
			try:
				start_pos_int = int(start_pos)
				end_pos_int = int(end_pos)
			except (TypeError, ValueError):
				continue
			canonical.append(
				{
					"original": norm.get("original"),
					"replacement": norm.get("replacement"),
					"start_pos": start_pos_int,
					"end_pos": end_pos_int,
					"context": norm.get("context", "question_stem"),
				}
			)
		canonical.sort(key=lambda item: (item["start_pos"], item["end_pos"], item["original"] or ""))
		return canonical

	def _resolve_option_text(self, question: QuestionManipulation, letter: Optional[str]) -> Optional[str]:
		if not letter or not isinstance(question.options_data, dict):
			return None
		for key, value in question.options_data.items():
			if self._extract_option_letter(key) == letter:
				return str(value)
		return None

	def _sanitize_signal_metadata(self, entry: Dict[str, Any]) -> Optional[Dict[str, str]]:
		original = str(entry.get("original") or "").strip()
		replacement = str(entry.get("replacement") or "").strip()
		signal_phrase = str(entry.get("signal_phrase") or "").strip()
		signal_type = str(entry.get("signal_type") or "").strip().lower()
		signal_notes = str(entry.get("signal_notes") or "").strip()

		if not signal_phrase:
			if original and replacement:
				signal_phrase = f"{original} -> {replacement}"
		else:
			normalized_phrase = signal_phrase.lower()
			if original and replacement:
				if normalized_phrase in {original.lower(), replacement.lower()}:
					signal_phrase = f"{original} -> {replacement}"

		if not signal_phrase:
			return None
		metadata = {"signal_phrase": signal_phrase}
		if signal_type:
			metadata["signal_type"] = signal_type
		if signal_notes:
			metadata["signal_notes"] = signal_notes
		return metadata

	def _detect_signal_in_answer(self, signal_metadata: Dict[str, str], answer: str) -> Optional[bool]:
		phrase = signal_metadata.get("signal_phrase")
		if not phrase:
			return None
		return phrase.casefold() in (answer or "").casefold()

	def _fallback_option_answer(self, question_model: QuestionManipulation) -> Optional[str]:
		options = question_model.options_data if isinstance(question_model.options_data, dict) else None
		if not options:
			return None
		gold_clean = (question_model.gold_answer or "").strip().lower()
		for opt_key in options.keys():
			key_clean = str(opt_key).strip().lower()
			if key_clean != gold_clean:
				return str(opt_key)
		first = next(iter(options.keys()), None)
		return str(first) if first is not None else None

	def _safe_page_index(self, value: object) -> Optional[int]:
		if value is None:
			return None
		try:
			page_int = int(value)
		except (TypeError, ValueError):
			return None
		if page_int < 0:
			return None
		if page_int == 0:
			return 0
		return page_int - 1

	def _resolve_pdf_path(self, run_id: str) -> Optional[Path]:
		structured = self.structured_manager.load(run_id)
		document_info = (structured or {}).get("document") or {}
		candidate = document_info.get("source_path")
		if candidate:
			path = Path(candidate)
			if path.exists():
				return path

		run = PipelineRun.query.get(run_id)
		if run and run.original_pdf_path:
			path = Path(run.original_pdf_path)
			if path.exists():
				return path

		return None

	def _get_structured_question(
		self,
		run_id: str,
		question_number: str,
		structured: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		structured = structured if structured is not None else self.structured_manager.load(run_id)
		for entry in (structured.get("questions") or []):
			label = str(entry.get("q_number") or entry.get("question_number") or "").strip()
			if label == str(question_number).strip():
				return entry
		return {}

	def _build_span_context(
		self,
		base: BaseRenderer,
		stem_text: str,
		mapping: Dict[str, Any],
		page_idx: int,
		stem_rect: Optional[fitz.Rect],
	) -> Optional[Dict[str, Any]]:
		original = base.strip_zero_width(str(mapping.get("original") or "")).strip()
		if not original:
			return None

		replacement = base.strip_zero_width(str(mapping.get("replacement") or "")).strip()
		context: Dict[str, Any] = {
			"original": original,
			"replacement": replacement,
			"context": mapping.get("context"),
			"page": page_idx,
		}

		normalized_original = base._normalize_for_span_match(original)
		if normalized_original:
			context["normalized_original"] = normalized_original
		normalized_replacement = base._normalize_for_span_match(replacement)
		if normalized_replacement:
			context["normalized_replacement"] = normalized_replacement
		fingerprint_key = mapping.get("fingerprint_key") or mapping.get("id")
		if fingerprint_key and not context.get("fingerprint_key"):
			context["fingerprint_key"] = fingerprint_key

		selection_page = mapping.get("selection_page")
		if isinstance(selection_page, int):
			context["selection_page"] = selection_page

		if stem_rect is not None and stem_rect.height >= 25 and stem_rect.width >= 25:
			context["stem_bbox"] = (
				float(stem_rect.x0),
				float(stem_rect.y0),
				float(stem_rect.x1),
				float(stem_rect.y1),
			)

		start_pos = mapping.get("start_pos")
		end_pos = mapping.get("end_pos")
		if (
			isinstance(start_pos, int)
			and isinstance(end_pos, int)
			and 0 <= start_pos <= end_pos <= len(stem_text)
		):
			prefix = stem_text[max(0, start_pos - 40) : start_pos]
			suffix = stem_text[end_pos : min(len(stem_text), end_pos + 40)]
			context.update(
				{
					"start_pos": start_pos,
					"end_pos": end_pos,
					"matched_text": stem_text[start_pos:end_pos],
					"prefix": prefix,
					"suffix": suffix,
				}
			)
			try:
				context["occurrence_index"] = stem_text[:start_pos].count(original)
			except Exception:
				pass
		else:
			context.setdefault("prefix", "")
			context.setdefault("suffix", "")

		selection_quads = mapping.get("selection_quads")
		if isinstance(selection_quads, list):
			context["selection_quads"] = selection_quads

		glyph_hint = mapping.get("matched_glyph_path") or mapping.get("selection_glyph_path")
		if isinstance(glyph_hint, dict):
			sanitized = self._sanitize_glyph_path(glyph_hint)
			if sanitized:
				context["matched_glyph_path"] = sanitized

		return context

	def _enrich_selection_geometry(
		self,
		run_id: str,
		question_model: QuestionManipulation,
		mappings: List[Dict[str, Any]],
		*,
		force_refresh: bool = False,
	) -> List[Dict[str, Any]]:
		if not mappings:
			return mappings

		structured = self.structured_manager.load(run_id)
		structured_question = self._get_structured_question(
			run_id,
			question_model.question_number,
			structured,
		)
		stem_text = (
			structured_question.get("stem_text")
			or structured_question.get("original_text")
			or question_model.original_text
			or ""
		)

		positioning = structured_question.get("positioning") or {}
		stem_position = question_model.stem_position or {}
		page_value = positioning.get("page") or stem_position.get("page")
		bbox_value = positioning.get("bbox") or stem_position.get("bbox")

		try:
			page_idx = self._safe_page_index(page_value)
		except Exception:
			page_idx = None

		if page_idx is None:
			# Attempt to derive from question index if available
			question_index = (structured.get("question_index") or [])
			for entry in question_index:
				if str(entry.get("q_number")) == str(question_model.question_number):
					page_idx = self._safe_page_index(entry.get("page"))
					stem = entry.get("stem") or {}
					bbox_value = bbox_value or stem.get("bbox")
					break

		span_index_data = structured.get("pymupdf_span_index") or []

		pdf_path = self._resolve_pdf_path(run_id)
		if pdf_path is None or page_idx is None:
			self.logger.warning(
				"auto_generate geometry unavailable",
				run_id=run_id,
				question_id=question_model.id,
				reason="missing_pdf_or_page",
			)
			return [self._normalize_mapping_entry(item) for item in mappings]

		try:
			doc = fitz.open(pdf_path)
		except Exception as exc:
			self.logger.warning(
				"auto_generate geometry open failed",
				run_id=run_id,
				question_id=question_model.id,
				pdf=str(pdf_path),
				error=str(exc),
			)
			return [self._normalize_mapping_entry(item) for item in mappings]

		try:
			page_obj = doc[page_idx]
		except Exception as exc:
			doc.close()
			self.logger.warning(
				"auto_generate geometry page lookup failed",
				run_id=run_id,
				question_id=question_model.id,
				page_index=page_idx,
				error=str(exc),
			)
			return [self._normalize_mapping_entry(item) for item in mappings]

		base = BaseRenderer()
		used_rects: List[fitz.Rect] = []
		stem_rect = None
		if isinstance(bbox_value, (list, tuple)) and len(bbox_value) == 4:
			try:
				stem_rect = fitz.Rect(*bbox_value)
			except Exception:
				stem_rect = None

		if force_refresh:
			recovered_page, recovered_bbox = base._recover_question_geometry(run_id, stem_text)
			if recovered_page is not None:
				page_idx = recovered_page
			if isinstance(recovered_bbox, (list, tuple)) and len(recovered_bbox) == 4:
				try:
					stem_rect = fitz.Rect(*recovered_bbox)
				except Exception:
					stem_rect = None
			else:
				stem_rect = None

		enriched: List[Dict[str, Any]] = []
		try:
			for mapping in mappings:
				norm = self._normalize_mapping_entry(mapping)
				if force_refresh:
					for key in (
						"selection_page",
						"selection_bbox",
						"selection_quads",
						"span_ids",
						"selection_span_ids",
						"vision_confidence",
						"geometry_source",
					):
						norm.pop(key, None)
				elif norm.get("selection_page") is not None and norm.get("selection_bbox"):
					enriched.append(norm)
					continue

				original = base.strip_zero_width(str(norm.get("original") or "")).strip()
				replacement = base.strip_zero_width(str(norm.get("replacement") or "")).strip()
				if not original or not replacement:
					enriched.append(norm)
					continue

				try:
					start_pos = int(norm.get("start_pos"))
					end_pos = int(norm.get("end_pos"))
				except (TypeError, ValueError):
					enriched.append(norm)
					continue

				context = self._build_span_context(base, stem_text, norm, page_idx, stem_rect)
				if not context:
					self.logger.warning(
						"auto_generate geometry context missing",
						run_id=run_id,
						question_id=question_model.id,
						mapping_id=norm.get("id"),
					)
					enriched.append(norm)
					continue

				location = base.locate_text_span(page_obj, context, used_rects)
				if not location:
					self.logger.warning(
						"auto_generate geometry locate failed",
						run_id=run_id,
						question_id=question_model.id,
						mapping_id=norm.get("id"),
						original=original,
					)
					enriched.append(norm)
					continue

				rect, _, _ = location
				used_rects.append(rect)
				norm["selection_page"] = page_idx
				norm["selection_bbox"] = [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]
				norm.setdefault(
					"selection_quads",
					[[rect.x0, rect.y0, rect.x1, rect.y0, rect.x1, rect.y1, rect.x0, rect.y1]],
				)
				glyph_path = context.get("matched_glyph_path")
				if isinstance(glyph_path, dict):
					sanitized = self._sanitize_glyph_path(glyph_path)
					if sanitized:
						norm["matched_glyph_path"] = sanitized
				enriched.append(norm)

			enriched = self._refresh_geometry_with_vision(
				run_id=run_id,
				question_model=question_model,
				structured=structured,
				structured_question=structured_question,
				stem_text=stem_text,
				page_idx=page_idx,
				page_obj=page_obj,
				base_renderer=base,
				span_index_data=span_index_data,
				mappings=enriched,
				used_rects=used_rects,
				stem_rect=stem_rect,
				force_refresh=force_refresh,
			)
		finally:
			doc.close()
		return enriched

	def _refresh_geometry_with_vision(
		self,
		*,
		run_id: str,
		question_model: QuestionManipulation,
		structured: Dict[str, Any],
		structured_question: Dict[str, Any],
		stem_text: str,
		page_idx: int,
		page_obj: fitz.Page,
		base_renderer: BaseRenderer,
		span_index_data: List[Dict[str, Any]],
		mappings: List[Dict[str, Any]],
		used_rects: List[fitz.Rect],
		stem_rect: Optional[fitz.Rect],
		force_refresh: bool = False,
	) -> List[Dict[str, Any]]:
		# Vision geometry refresh disabled - using full page overlays for LaTeX attacks
		# No need for precise bounding boxes since entire pages are overlaid
		return mappings

		page_number = page_idx + 1
		scale = self._vision_geometry_scale if self._vision_geometry_scale > 0 else 1.0

		vision_mappings: List[Dict[str, Any]] = []

		for index, norm in enumerate(mappings):
			original = base_renderer.strip_zero_width(str(norm.get("original") or "")).strip()
			replacement = base_renderer.strip_zero_width(str(norm.get("replacement") or "")).strip()
			if not original or not replacement:
				continue

			try:
				start_pos = int(norm.get("start_pos"))
				end_pos = int(norm.get("end_pos"))
			except (TypeError, ValueError):
				continue

			if end_pos <= start_pos:
				continue

			occurrence = base_renderer._compute_occurrence_index(stem_text, original, start_pos)
			prefix = stem_text[max(0, start_pos - 40) : start_pos]
			suffix = stem_text[end_pos : min(len(stem_text), end_pos + 40)]
			key = (original, occurrence)
			norm["_vision_key"] = key
			norm["_vision_range"] = (start_pos, end_pos)
			vision_mappings.append(
				{
					"substring": original,
					"occurrence": occurrence,
					"start_pos": start_pos,
					"end_pos": end_pos,
					"prefix": prefix,
					"suffix": suffix,
				}
			)

		if not vision_mappings:
			for norm in mappings:
				norm.pop("_vision_key", None)
				norm.pop("_vision_range", None)
			return mappings

		try:
			pixmap = page_obj.get_pixmap(matrix=fitz.Matrix(scale, scale))
			page_image = pixmap.tobytes("png")
		except Exception as exc:  # noqa: BLE001
			self.logger.warning(
				"vision geometry render failed",
				run_id=run_id,
				question_id=question_model.id,
				error=str(exc),
			)
			for norm in mappings:
				norm.pop("_vision_key", None)
				norm.pop("_vision_range", None)
			return mappings

		question_payload = [
			{
				"question_number": str(question_model.question_number),
				"stem_text": stem_text,
				"mappings": vision_mappings,
			}
		]

		retry_attempted = False
		while True:
			try:
				vision_response = self.vision_client.locate_mapping_geometry(
					page_image,
					page_number,
					question_payload,
					run_id=run_id,
				)
			except Exception as exc:  # noqa: BLE001
				self.logger.warning(
					"vision geometry request failed",
					run_id=run_id,
					question_id=question_model.id,
					error=str(exc),
				)
				for norm in mappings:
					norm.pop("_vision_key", None)
					norm.pop("_vision_range", None)
				return mappings

			truncated_hits: List[Dict[str, Any]] = []
			for entry in vision_response.get("geometry", []) or []:
				candidate_rect = self._rect_from_bbox_pixels(entry.get("bbox"), scale)
				if candidate_rect is None:
					continue
				if candidate_rect.width <= 1.2 or candidate_rect.height <= 1.2:
					truncated_hits.append(
						{
							"question_number": entry.get("question_number"),
							"substring": entry.get("substring"),
							"occurrence": entry.get("occurrence"),
							"width": round(float(candidate_rect.width), 3),
							"height": round(float(candidate_rect.height), 3),
						},
					)

			if truncated_hits and not retry_attempted:
				retry_attempted = True
				question_payload[0]["retry_hint"] = {
					"reason": "bbox_too_small",
					"targets": truncated_hits,
				}
				self.logger.info(
					"vision geometry retry triggered",
					run_id=run_id,
					question_id=question_model.id,
					retry_reason="bbox_too_small",
					targets=len(truncated_hits),
				)
				continue

			break

		geometry_matches: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
		for item in vision_response.get("geometry", []) or []:
			if not isinstance(item, dict):
				continue
			substring = base_renderer.strip_zero_width(str(item.get("substring") or "")).strip()
			if not substring:
				continue
			occ_raw = item.get("occurrence")
			try:
				occurrence_val = int(occ_raw)
			except (TypeError, ValueError):
				occurrence_val = 0
			geometry_matches[(substring, occurrence_val)].append(item)

		for warning in vision_response.get("warnings", []) or []:
			if isinstance(warning, dict):
				self.logger.warning(
					"vision mapping warning",
					run_id=run_id,
					question_id=question_model.id,
					substring=warning.get("substring"),
					occurrence=warning.get("occurrence"),
					reason=warning.get("reason"),
				)

		page_span_records = self._get_page_spans(span_index_data, page_number)
		geometry_updated = False
		vision_rects: List[fitz.Rect] = []
		span_map = {str(record.get("id")): record for record in page_span_records}

		for norm in mappings:
			key = norm.pop("_vision_key", None)
			norm.pop("_vision_range", None)
			if not key:
				continue
			entries = geometry_matches.get(key)
			if not entries:
				continue
			geometry_entry = entries.pop(0)
			rect = self._rect_from_bbox_pixels(geometry_entry.get("bbox"), scale)
			if rect is None:
				self.logger.warning(
					"vision geometry invalid bbox",
					run_id=run_id,
					question_id=question_model.id,
					substring=key[0],
				)
				continue

			expanded_rect = self._expand_rect(rect, self._vision_geometry_margin, page_obj.rect)
			span_ids = self._resolve_span_ids_from_rect(page_span_records, expanded_rect)
			span_ids = list(dict.fromkeys(span_ids))
			final_rect = expanded_rect
			geometry_source = "openai_vision_refresh"

			combined_text = base_renderer._collect_span_text(span_map, span_ids)
			if not span_ids or not base_renderer._substring_in_text(key[0], combined_text):
				prefix_hint = norm.get("prefix")
				suffix_hint = norm.get("suffix")
				fallback_result = base_renderer._fallback_span_ids_by_text(
					page_span_records,
					span_map,
					key[0],
					prefix_hint,
					suffix_hint,
					key[1],
				)
				if fallback_result:
					span_ids, fallback_rect = fallback_result
					span_ids = list(dict.fromkeys(span_ids))
					if fallback_rect is not None:
						final_rect = fallback_rect
					else:
						final_rect = base_renderer._union_rect_for_span_ids(span_map, span_ids)
					geometry_source = "vision_text_fallback"
				else:
					relaxed_hits = base_renderer._find_occurrences(
						page_obj,
						key[0],
						clip_rect=expanded_rect,
					)
					if not relaxed_hits:
						widened_rect = self._expand_rect(
							expanded_rect,
							max(self._vision_geometry_margin * 1.5, 18.0),
							page_obj.rect,
						)
						relaxed_hits = base_renderer._find_occurrences(
							page_obj,
							key[0],
							clip_rect=widened_rect,
						)

					if relaxed_hits:
						ref_cx = (expanded_rect.x0 + expanded_rect.x1) / 2.0
						ref_cy = (expanded_rect.y0 + expanded_rect.y1) / 2.0
						def _hit_distance(hit: Dict[str, Any]) -> float:
							rect_hit = hit.get("rect")
							if not isinstance(rect_hit, fitz.Rect):
								rect_hit = fitz.Rect(rect_hit)
							cx = (rect_hit.x0 + rect_hit.x1) / 2.0
							cy = (rect_hit.y0 + rect_hit.y1) / 2.0
							return (cx - ref_cx) ** 2 + (cy - ref_cy) ** 2

						best_hit = min(relaxed_hits, key=_hit_distance)
						candidate_rect = best_hit.get("rect")
						if candidate_rect is not None and not isinstance(candidate_rect, fitz.Rect):
							candidate_rect = fitz.Rect(candidate_rect)

						if isinstance(candidate_rect, fitz.Rect):
							anchored_rect = self._expand_rect(candidate_rect, self._vision_geometry_margin / 2.0, page_obj.rect)
							span_ids = self._resolve_span_ids_from_rect(page_span_records, anchored_rect)
							span_ids = list(dict.fromkeys(span_ids))
							if not span_ids:
								alt_result = base_renderer._fallback_span_ids_by_text(
									page_span_records,
									span_map,
									key[0],
									prefix_hint,
									suffix_hint,
									key[1],
								)
								if alt_result:
									span_ids, fallback_rect = alt_result
									span_ids = list(dict.fromkeys(span_ids))
									candidate_rect = fallback_rect or base_renderer._union_rect_for_span_ids(span_map, span_ids)
							if span_ids:
								final_rect = candidate_rect if candidate_rect is not None else anchored_rect
								geometry_source = "vision_relaxed_occurrence"
							else:
								self.logger.warning(
									"vision geometry missing span overlap",
									run_id=run_id,
									question_id=question_model.id,
									substring=key[0],
									reason="relaxed_occurrence_no_spans",
								)
								continue
					else:
						self.logger.warning(
							"vision geometry missing span overlap",
							run_id=run_id,
							question_id=question_model.id,
							substring=key[0],
							reason="substring_not_found",
						)
						continue

			if not span_ids:
				self.logger.warning(
					"vision geometry missing span overlap",
					run_id=run_id,
					question_id=question_model.id,
					substring=key[0],
					reason="no_span_ids",
				)
				continue

			if final_rect is None:
				final_rect = base_renderer._union_rect_for_span_ids(span_map, span_ids)
			if final_rect is None:
				self.logger.warning(
					"vision geometry unable to derive bbox",
					run_id=run_id,
					question_id=question_model.id,
					substring=key[0],
				)
				continue

			bbox_list = [
				float(final_rect.x0),
				float(final_rect.y0),
				float(final_rect.x1),
				float(final_rect.y1),
			]

			norm["selection_page"] = page_idx
			norm["selection_bbox"] = bbox_list
			norm["selection_quads"] = [self._rect_to_quad(final_rect)]
			norm["span_ids"] = span_ids
			norm["selection_span_ids"] = span_ids

			if geometry_source == "vision_text_fallback":
				try:
					live_logging_service.emit(
						run_id,
						"smart_substitution",
						"WARNING",
						"vision geometry text fallback used",
						context={
							"question_number": question_model.question_number,
							"mapping_id": norm.get("id"),
							"substring": key[0],
							"occurrence": key[1],
							"page": page_idx + 1,
						},
						component="geometry_refresh",
					)
				except Exception:
					self.logger.warning(
						"vision geometry text fallback used",
						run_id=run_id,
						question_id=question_model.id,
						mapping_id=norm.get("id"),
					)
			elif geometry_source == "vision_relaxed_occurrence":
				try:
					live_logging_service.emit(
						run_id,
						"smart_substitution",
						"INFO",
						"vision geometry relaxed occurrence used",
						context={
							"question_number": question_model.question_number,
							"mapping_id": norm.get("id"),
							"substring": key[0],
							"occurrence": key[1],
							"page": page_idx + 1,
						},
						component="geometry_refresh",
					)
				except Exception:
					self.logger.info(
						"vision geometry relaxed occurrence used",
						run_id=run_id,
						question_id=question_model.id,
						mapping_id=norm.get("id"),
					)

			if geometry_source == "openai_vision_refresh":
				norm["geometry_source"] = geometry_source
				confidence = geometry_entry.get("confidence")
				if confidence is not None:
					try:
						norm["vision_confidence"] = float(confidence)
					except (TypeError, ValueError):
						pass
			else:
				norm["geometry_source"] = geometry_source
				norm.pop("vision_confidence", None)

			vision_rects.append(final_rect)
			used_rects.append(final_rect)
			geometry_updated = True

		updated_stem_rect = stem_rect
		if vision_rects:
			combined = vision_rects[0]
			for rect in vision_rects[1:]:
				combined |= rect
			if updated_stem_rect is None:
				updated_stem_rect = combined
			else:
				updated_stem_rect |= combined

		stem_span_ids: List[str] = []
		if updated_stem_rect is not None:
			stem_span_ids = self._resolve_span_ids_from_rect(page_span_records, updated_stem_rect)

		positioning = structured_question.setdefault("positioning", {}) if structured_question is not None else {}
		if updated_stem_rect is not None:
			stem_bbox_list = [
				float(updated_stem_rect.x0),
				float(updated_stem_rect.y0),
				float(updated_stem_rect.x1),
				float(updated_stem_rect.y1),
			]
			positioning["page"] = positioning.get("page") or page_number
			positioning["bbox"] = stem_bbox_list
			structured_question["stem_bbox"] = stem_bbox_list
			if stem_span_ids:
				geometry_updated = True
				structured_question["stem_spans"] = list(dict.fromkeys(stem_span_ids))
				positioning["stem_spans"] = list(dict.fromkeys(stem_span_ids))
				question_model.stem_position = question_model.stem_position or {}
				question_model.stem_position.update(
					{
						"page": page_number,
						"bbox": stem_bbox_list,
						"span_ids": list(dict.fromkeys(stem_span_ids)),
						"stem_spans": list(dict.fromkeys(stem_span_ids)),
					}
				)
			elif question_model.stem_position:
				question_model.stem_position.setdefault("page", page_number)
				question_model.stem_position.setdefault("bbox", stem_bbox_list)

		if geometry_updated:
			structured_question.setdefault("manipulation", {})
			structured_question["manipulation"]["substring_mappings"] = mappings
			try:
				self.structured_manager.save(run_id, structured)
			except Exception as exc:  # noqa: BLE001
				self.logger.warning(
					"vision geometry save failed",
					run_id=run_id,
					question_id=question_model.id,
					error=str(exc),
				)
			self.logger.info(
				"vision geometry refresh applied",
				run_id=run_id,
				question_id=question_model.id,
				substrings=len(vision_mappings),
				warnings=len(vision_response.get("warnings", []) or []),
			)

		return mappings

	def _rect_from_bbox_pixels(self, bbox: Any, scale: float) -> Optional[fitz.Rect]:
		if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
			return None
		try:
			x0, y0, x1, y1 = [float(value) for value in bbox]
		except (TypeError, ValueError):
			return None
		divisor = scale if scale and scale > 0 else 1.0
		x0_pdf = x0 / divisor
		y0_pdf = y0 / divisor
		x1_pdf = x1 / divisor
		y1_pdf = y1 / divisor
		rect = fitz.Rect(min(x0_pdf, x1_pdf), min(y0_pdf, y1_pdf), max(x0_pdf, x1_pdf), max(y0_pdf, y1_pdf))
		return rect

	def _expand_rect(self, rect: fitz.Rect, margin: float, page_rect: fitz.Rect) -> fitz.Rect:
		margin = max(0.0, margin)
		expanded = fitz.Rect(
			rect.x0 - margin,
			rect.y0 - margin,
			rect.x1 + margin,
			rect.y1 + margin,
		)
		expanded.x0 = max(page_rect.x0, expanded.x0)
		expanded.y0 = max(page_rect.y0, expanded.y0)
		expanded.x1 = min(page_rect.x1, expanded.x1)
		expanded.y1 = min(page_rect.y1, expanded.y1)
		if expanded.x0 >= expanded.x1 or expanded.y0 >= expanded.y1:
			return rect
		return expanded

	def _rect_to_quad(self, rect: fitz.Rect) -> List[float]:
		return [
			float(rect.x0),
			float(rect.y0),
			float(rect.x1),
			float(rect.y0),
			float(rect.x1),
			float(rect.y1),
			float(rect.x0),
			float(rect.y1),
		]

	def _get_page_spans(
		self,
		span_index_data: List[Dict[str, Any]],
		page_number: int,
	) -> List[Dict[str, Any]]:
		for entry in span_index_data:
			try:
				entry_page = int(entry.get("page"))
			except (TypeError, ValueError):
				continue
			if entry_page == page_number:
				spans = entry.get("spans")
				if isinstance(spans, list):
					return spans
		return []

	def _resolve_span_ids_from_rect(
		self,
		span_records: List[Dict[str, Any]],
		target_rect: fitz.Rect,
	) -> List[str]:
		if not span_records:
			return []

		hits: List[Tuple[float, float, str]] = []
		for span in span_records:
			bbox = span.get("bbox")
			if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
				continue
			try:
				span_rect = fitz.Rect(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
			except Exception:
				continue
			if not target_rect.intersects(span_rect):
				continue
			hits.append((span_rect.y0, span_rect.x0, str(span.get("id"))))

		if not hits:
			return []
		hits.sort()
		ordered = [hit[2] for hit in hits]
		return list(dict.fromkeys(ordered))

	def _resolve_float_env(self, name: str, default: float, *, minimum: Optional[float] = None) -> float:
		value = os.getenv(name)
		if value is None:
			return default
		try:
			parsed = float(value)
		except ValueError:
			return default
		if minimum is not None and parsed < minimum:
			return default
		return parsed

	def _resolve_int_env(self, name: str, default: int, *, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
		value = os.getenv(name)
		if value is None:
			return default
		try:
			parsed = int(value)
		except ValueError:
			return default
		if minimum is not None and parsed < minimum:
			parsed = minimum
		if maximum is not None and parsed > maximum:
			parsed = maximum
		return parsed

	def refresh_question_mapping(self, run_id: str, question_identifier: str) -> Dict[str, Any]:
		structured = self.structured_manager.load(run_id)
		strategy = structured.get("global_mappings", {}).get("character_strategy", "unicode_steganography")
		mapping_result = self.mapper.create_mapping(strategy)

		questions = structured.get("questions", [])
		question_model = None
		try:
			question_model = QuestionManipulation.query.filter_by(
				pipeline_run_id=run_id, id=int(question_identifier)
			).first()
		except (TypeError, ValueError):
			question_model = None

		if question_model is None:
			question_model = QuestionManipulation.query.filter_by(
				pipeline_run_id=run_id, question_number=str(question_identifier)
			).first()

		if not question_model:
			raise ValueError("Question manipulation entry missing")

		question_dict = next((q for q in questions if q.get("manipulation_id") == question_model.id), None)
		if question_dict is None:
			question_dict = next(
				(q for q in questions if str(q.get("q_number") or q.get("question_number")) == str(question_model.question_number)),
				None,
			)

		if not question_dict:
			raise ValueError("Question not found in structured data")

		# Ensure list exists and is JSON-safe - use mutation-only approach
		current_list: List[Dict[str, Any]] = list(question_model.substring_mappings or [])
		json_safe = json.loads(json.dumps(current_list))
		# Only mutate existing MutableList, never assign new list directly
		if question_model.substring_mappings is not None:
			question_model.substring_mappings.clear()
			question_model.substring_mappings.extend(json_safe)
		question_model.effectiveness_score = aggregate_effectiveness(json_safe)
		db.session.add(question_model)
		db.session.commit()

		self._merge_question_payload(question_dict, question_model)
		question_dict["manipulation"] = question_dict.get("manipulation", {})
		question_dict["manipulation"].update(
			{
				"substring_mappings": json_safe,
				"effectiveness_score": question_model.effectiveness_score,
				"method": question_model.manipulation_method or "smart_substitution",
				"character_strategy": mapping_result.strategy,
			}
		)
		self.structured_manager.save(run_id, structured)
		return {
			"substring_mappings": json_safe,
			"effectiveness_score": question_model.effectiveness_score,
		}

	def sync_structured_mappings(self, run_id: str) -> None:
		"""Ensure structured data reflects the latest substring mappings from the database."""
		structured = self.structured_manager.load(run_id)
		if not structured:
			return

		questions = structured.setdefault("questions", [])
		if not questions:
			return

		strategy = structured.get("global_mappings", {}).get("character_strategy", "unicode_steganography")

		changed = False
		for model in (
			QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
			.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
			.all()
		):
			question_map_by_id = {
				entry.get("manipulation_id"): entry for entry in questions if entry.get("manipulation_id") is not None
			}
			question_map_by_seq = {
				entry.get("sequence_index"): entry for entry in questions if entry.get("sequence_index") is not None
			}
			question_map_by_label = {
				str(entry.get("q_number") or entry.get("question_number") or ""): entry for entry in questions
			}

			entry = question_map_by_id.get(model.id)
			if entry is None:
				entry = question_map_by_seq.get(model.sequence_index)
			if entry is None:
				entry = question_map_by_label.get(str(model.question_number or ""))
			if entry is None:
				entry = {}
				questions.append(entry)
				changed = True

			self._merge_question_payload(entry, model)

			current_list: List[Dict[str, Any]] = [
				self._normalize_mapping_entry(item) for item in list(model.substring_mappings or [])
			]
			try:
				enriched_list = self._enrich_selection_geometry(run_id, model, current_list)
			except ValueError:
				enriched_list = current_list

			if enriched_list != current_list:
				db.session.execute(
					text("UPDATE question_manipulations SET substring_mappings = :mappings WHERE id = :id"),
					{"mappings": json.dumps(enriched_list), "id": model.id},
				)
				current_list = enriched_list
				changed = True

			for entry in current_list:
				letter = self._extract_option_letter(entry.get("target_option")) if isinstance(entry, dict) else None
				if letter:
					entry["target_option"] = letter
					resolved_text = entry.get("target_option_text") or self._resolve_option_text(model, letter)
					if resolved_text:
						entry["target_option_text"] = resolved_text
				else:
					entry.pop("target_option", None)
					entry.pop("target_option_text", None)
				signal_meta = self._sanitize_signal_metadata(entry) if isinstance(entry, dict) else None
				if signal_meta:
					entry.update(signal_meta)
				else:
					if isinstance(entry, dict):
						for key in ("signal_type", "signal_phrase", "signal_notes"):
							entry.pop(key, None)

			json_safe = json.loads(json.dumps(current_list))
			manipulation = entry.get("manipulation") or {}
			previous = manipulation.get("substring_mappings") or []
			if previous != json_safe:
				changed = True

			manipulation.update(
				{
					"substring_mappings": json_safe,
					"effectiveness_score": model.effectiveness_score,
					"method": model.manipulation_method or "smart_substitution",
					"character_strategy": strategy,
				}
			)
			entry["manipulation"] = manipulation

		questions.sort(
			key=lambda entry: (
				entry.get("sequence_index") if isinstance(entry.get("sequence_index"), int) else 0,
				str(entry.get("manipulation_id") or entry.get("q_number") or entry.get("question_number") or ""),
			)
		)

		# Always save to ensure mappings are persisted
		self.structured_manager.save(run_id, structured)

	def promote_staged_mappings(self, run_id: str) -> Dict[str, Any]:
		"""Promote staged mappings into the canonical question store."""
		staged = self.staging_service.load(run_id)
		entries = (staged or {}).get("questions", {}) if staged else {}
		if not entries:
			return {"promoted": [], "skipped": [], "total_promoted": 0}

		questions = (
			QuestionManipulation.query.filter_by(pipeline_run_id=run_id)
			.order_by(QuestionManipulation.sequence_index.asc(), QuestionManipulation.id.asc())
			.all()
		)
		questions_by_id = {str(q.id): q for q in questions}

		promoted_ids: List[int] = []
		promoted_numbers: List[str] = []
		promoted_payloads: List[Tuple[int, str, List[Dict[str, Any]]]] = []
		skipped: List[Dict[str, Any]] = []

		for question_id_str, entry in entries.items():
			question = questions_by_id.get(question_id_str)
			if not question:
				continue

			status = entry.get("status")
			if status == "validated":
				mapping_payload = entry.get("staged_mapping")
				if not mapping_payload:
					skipped.append(
						{
							"question_number": str(question.question_number),
							"status": "validated",
							"reason": "staged mapping missing",
						}
					)
					continue

				json_safe = json.loads(json.dumps([mapping_payload]))
				question.substring_mappings = json_safe
				question.manipulation_method = entry.get("method") or "gpt5_generated"

				summary = entry.get("validation_summary") or {}
				effectiveness = summary.get("confidence")
				if isinstance(effectiveness, (int, float)):
					question.effectiveness_score = float(effectiveness)
				else:
					question.effectiveness_score = None

				db.session.add(question)
				db.session.execute(
					text("UPDATE question_manipulations SET substring_mappings = :mappings WHERE id = :id"),
					{"mappings": json.dumps(json_safe), "id": question.id},
				)
				promoted_ids.append(question.id)
				promoted_numbers.append(str(question.question_number))
				promoted_payloads.append((question.id, str(question.question_number), json_safe))
			else:
				reason = entry.get("skip_reason") or entry.get("error") or status or "unknown"
				skipped.append(
					{
						"question_number": str(question.question_number),
						"status": status or "unknown",
						"reason": reason,
					}
				)

		db.session.commit()

		if promoted_ids:
			self.sync_structured_mappings(run_id)
			consistency_issues = self._verify_promotion_consistency(run_id, promoted_payloads)
			if consistency_issues:
				self.logger.error(
					"Promotion consistency check failed",
					extra={
						"run_id": run_id,
						"issues": consistency_issues,
					},
				)
				raise RuntimeError(
					"Validated mappings could not be synchronized to the database and structured data. "
					"Please retry after resolving the reported issues."
				)
			self.staging_service.mark_promoted(run_id, promoted_ids)

		structured = self.structured_manager.load(run_id) or {}
		manipulation_results = structured.setdefault("manipulation_results", {})
		manipulation_results["staged_promoted_questions"] = promoted_numbers
		manipulation_results["staged_skipped_questions"] = skipped
		self.structured_manager.save(run_id, structured)

		self.logger.info(
			"Promoted staged mappings",
			extra={
				"run_id": run_id,
				"promoted": promoted_numbers,
				"skipped": skipped,
			},
		)

		return {
			"promoted": promoted_numbers,
			"skipped": skipped,
			"total_promoted": len(promoted_numbers),
		}

	def _verify_promotion_consistency(
		self,
		run_id: str,
		promoted_payloads: List[Tuple[int, str, List[Dict[str, Any]]]],
	) -> List[Dict[str, Any]]:
		if not promoted_payloads:
			return []

		id_list = [question_id for question_id, _, _ in promoted_payloads]
		db_models = {
			model.id: json.loads(json.dumps(model.substring_mappings or []))
			for model in QuestionManipulation.query.filter(QuestionManipulation.id.in_(id_list)).all()
		}

		structured = self.structured_manager.load(run_id) or {}
		structured_questions = structured.get("questions") or []
		structured_index: Dict[str, Dict[str, Any]] = {}

		for entry in structured_questions:
			key = str(entry.get("q_number") or entry.get("question_number") or "").strip()
			if not key:
				continue
			mappings = (entry.get("manipulation") or {}).get("substring_mappings") or []
			existing = structured_index.get(key)
			if not existing or not ((existing.get("manipulation") or {}).get("substring_mappings")):
				structured_index[key] = entry

		issues: List[Dict[str, Any]] = []
		for question_id, question_number, expected in promoted_payloads:
			actual_db = db_models.get(question_id, [])
			if self._canonicalize_mappings_for_compare(actual_db) != self._canonicalize_mappings_for_compare(expected):
				issues.append(
					{
						"type": "database_mismatch",
						"question_id": question_id,
						"question_number": question_number,
					}
				)

			structured_entry = structured_index.get(question_number)
			structured_mappings: List[Dict[str, Any]] = []
			if structured_entry:
				structured_mappings = json.loads(
					json.dumps(
						(structured_entry.get("manipulation") or {}).get("substring_mappings") or []
					)
				)
			if self._canonicalize_mappings_for_compare(structured_mappings) != self._canonicalize_mappings_for_compare(expected):
				issues.append(
					{
						"type": "structured_mismatch",
						"question_id": question_id,
						"question_number": question_number,
					}
				)

		return issues

	def _compute_true_gold(self, question: QuestionManipulation) -> tuple[str | None, float | None]:
		options = question.options_data or {}
		if not options:
			return (None, None)
		if not self.ai_client.is_configured():
			# heuristic fallback
			first_label = next(iter(options.keys()), None)
			return (first_label, 0.5 if first_label else None)
		prompt = f"Question: {question.original_text}\n"
		if options:
			prompt += "Options:\n"
			for k, v in options.items():
				prompt += f"{k}. {v}\n"
		prompt += "\nReturn only the final answer letter."
		# Use GPT-5.1 explicitly for gold answer computation to avoid gpt-4o conversion
		res = self.ai_client.call_model(provider="openai:gpt-5.1", payload={"prompt": prompt})
		ans = (res or {}).get("response")
		return (str(ans).strip() if ans else None, 0.9 if ans else None)


def _auto_generate_for_question_impl(
    *,
    service: "SmartSubstitutionService",
    run_id: str,
    question_model: QuestionManipulation,
    provider: str,
    structured: Optional[Dict[str, Any]],
    max_completion_tokens: int,
    force_refresh: bool,
) -> AutoMappingOutcome:
    structured_data = structured if structured is not None else service.structured_manager.load(run_id)
    ai_questions = (structured_data or {}).get("ai_questions", []) if structured_data else []
    ai_index = {
        str(q.get("question_number") or q.get("q_number") or "").strip(): q
        for q in ai_questions
    }
    label = str(question_model.question_number).strip()
    rich = ai_index.get(label, {})

    stem_text = (
        rich.get("stem_text")
        or question_model.original_text
        or ""
    )
    if not stem_text:
        raise ValueError("Question stem unavailable for mapping generation")

    options = rich.get("options") or question_model.options_data or {}
    if isinstance(options, dict):
        options_block = "\n".join(f"{k}. {v}" for k, v in options.items())
    else:
        options_block = ""

    question_type = question_model.question_type or rich.get("question_type") or "mcq_single"
    gold_answer = question_model.gold_answer or rich.get("gold_answer")
    strategy_definition = get_strategy(question_type)
    index_reference = build_index_reference(stem_text)

    positioning_info = rich.get("positioning") or {}
    page_hint = positioning_info.get("page") or rich.get("page_number")
    if page_hint is None:
        stem_position = question_model.stem_position or {}
        page_hint = stem_position.get("page")
    page_index = 0
    if page_hint is not None:
        try:
            page_index = int(page_hint)
        except (TypeError, ValueError):
            page_index = 0
        else:
            if page_index > 0:
                page_index -= 1
    page_index = max(page_index, 0)

    stem_bbox = rich.get("stem_bbox")
    if not stem_bbox:
        stem_position = question_model.stem_position or {}
        stem_bbox = stem_position.get("bbox")

    keyword_set: set[str] = set()
    if stem_text:
        for token in re.findall(r"[A-Za-z0-9\(\)\^\-]+", stem_text):
            if token:
                keyword_set.add(token.lower())
    if isinstance(options, dict):
        for value in options.values():
            for token in re.findall(r"[A-Za-z0-9\(\)\^\-]+", value):
                if token:
                    keyword_set.add(token.lower())
    keyword_set.add(label.lower())

    safe_span_entries = service._collect_safe_span_candidates(
        structured_data,
        page_index,
        stem_bbox if isinstance(stem_bbox, list) else None,
        sorted(keyword_set),
    )
    text_span_entries = service._build_text_span_candidates(stem_text)
    if text_span_entries:
        seen_texts = {entry.get("text"): True for entry in text_span_entries}
        for entry in safe_span_entries:
            candidate_text = entry.get("text")
            if candidate_text and candidate_text in seen_texts:
                continue
            text_span_entries.append(entry)
        safe_span_entries = text_span_entries
        if len(safe_span_entries) > 80:
            safe_span_entries = safe_span_entries[:80]

    top_k = max(1, service._resolve_int_env("AUTO_MAPPING_TOP_K", 3, minimum=1, maximum=10))
    max_rounds = max(1, service._resolve_int_env("AUTO_MAPPING_MAX_ROUNDS", 2, minimum=1, maximum=5))
    strategy_validation_focus = describe_strategy_for_validation(strategy_definition)

    base_prompt = build_generation_prompt(
        stem_text=stem_text,
        question_type=question_type,
        gold_answer=gold_answer,
        options_block=options_block,
        strategy=strategy_definition,
        index_reference=index_reference,
        safe_span_entries=safe_span_entries,
        max_candidates=top_k,
    )

    token_limit = min(max_completion_tokens, 4000)
    feedback_notes: List[str] = []
    avoid_substrings: set[str] = set()
    require_option_change = False
    attempt_logs: List[Dict[str, Any]] = []
    prompt_history: List[str] = []
    all_inferred_ranges: List[Dict[str, Any]] = []
    all_skipped_entries: List[Dict[str, Any]] = []
    selected_mapping: Optional[Dict[str, Any]] = None
    selected_candidate_rank: Optional[int] = None
    selected_round: Optional[int] = None
    final_raw_content = ""
    final_parsed_payload: Dict[str, Any] = {}
    final_raw_response: Optional[Dict[str, Any]] = None
    fallback_used = False
    strategy_used_global = strategy_definition.key
    provider_used = provider

    available_option_letters: set[str] = set()
    if isinstance(question_model.options_data, dict):
        for key in question_model.options_data.keys():
            if key is None:
                continue
            letter = service._extract_option_letter(key)
            if letter:
                available_option_letters.add(letter)
    gold_letter_for_feedback = service._extract_option_letter(question_model.gold_answer)
    if gold_letter_for_feedback and gold_letter_for_feedback in available_option_letters:
        available_option_letters.discard(gold_letter_for_feedback)

    attempted_target_options: set[str] = set()

    for round_index in range(max_rounds):
        prompt_to_use = service._augment_prompt_with_feedback(
            base_prompt,
            feedback_notes,
            avoid_substrings=avoid_substrings,
            require_option_change=require_option_change,
            gold_answer=question_model.gold_answer,
        )
        prompt_history.append(prompt_to_use)
        payload = {
            "prompt": prompt_to_use,
            "response_format": {"type": "json_object"},
            "generation_options": {
                "max_completion_tokens": token_limit,
                "max_output_tokens": token_limit,
            },
        }

        generation = service._invoke_generation_call(
            payload=payload,
            provider=provider,
            strategy_definition=strategy_definition,
            stem_text=stem_text,
            question_type=question_type,
            run_id=run_id,
            question_model=question_model,
        )

        fallback_used = fallback_used or generation.fallback_used
        provider_used = generation.provider_used
        if generation.strategy_used:
            strategy_used_global = generation.strategy_used

        normalized_entries, inferred_ranges, skipped_entries = service._normalize_ai_mappings(
            stem_text,
            generation.mappings_payload,
        )
        all_inferred_ranges.extend(inferred_ranges)
        all_skipped_entries.extend(skipped_entries)

        if not normalized_entries:
            feedback_notes.append(
                "No viable mapping candidates were produced. Propose a different contiguous substring that clearly flips the answer."
            )
            continue

        candidate_iterable = list(enumerate(normalized_entries))
        candidate_success = False

        for candidate_index, candidate in candidate_iterable[:top_k]:
            candidate_copy = dict(candidate)
            enriched_candidates = service._enrich_selection_geometry(
                run_id,
                question_model,
                [candidate_copy],
                # Always refresh geometry so snapshot overlays align with the latest span
                force_refresh=True,
            )
            if not enriched_candidates:
                if candidate.get("original"):
                    avoid_substrings.add(str(candidate.get("original")))
                attempt_logs.append(
                    {
                        "round": round_index,
                        "candidate_rank": candidate_index,
                        "original": candidate.get("original"),
                        "replacement": candidate.get("replacement"),
                        "target_option": candidate.get("target_option"),
                        "target_option_text": candidate.get("target_option_text"),
                        "signal_phrase": candidate.get("signal_phrase"),
                        "signal_type": candidate.get("signal_type"),
                        "validated": False,
                        "reason": "geometry_unavailable",
                    }
                )
                feedback_notes.append(
                    f"Unable to align span for '{candidate.get('original')}' in the PDF. Choose a different substring."
                )
                continue

            enriched_candidate = enriched_candidates[0]
            validated_mapping, validation_record, validation_result, test_answer = service._validate_candidate_mapping(
                run_id=run_id,
                question_model=question_model,
                mapping=enriched_candidate,
                stem_text=stem_text,
                strategy_key=strategy_used_global,
                strategy_validation_focus=strategy_validation_focus,
                provider=provider_used,
            )

            candidate_target_letter = service._extract_option_letter(candidate.get("target_option"))
            if candidate_target_letter:
                attempted_target_options.add(candidate_target_letter)

            validated_target_letter = service._extract_option_letter(validated_mapping.get("target_option"))
            if validated_target_letter:
                attempted_target_options.add(validated_target_letter)
            validated_test_letter = service._extract_option_letter(validated_mapping.get("test_option"))
            if validated_test_letter:
                attempted_target_options.add(validated_test_letter)

            attempt_logs.append(
                {
                    "round": round_index,
                    "candidate_rank": candidate_index,
                    "original": candidate.get("original"),
                    "replacement": candidate.get("replacement"),
                    "target_option": candidate.get("target_option"),
                    "target_option_text": candidate.get("target_option_text"),
                    "signal_phrase": candidate.get("signal_phrase"),
                    "signal_type": candidate.get("signal_type"),
                    "validated": validation_result.is_valid,
                    "confidence": validation_result.confidence,
                    "reasoning": validation_result.reasoning,
                    "test_answer": test_answer,
                    "target_matched": validation_result.target_matched,
                    "signal_detected": validation_result.signal_detected,
                    "diagnostics": validation_result.diagnostics,
                }
            )

            if validation_result.is_valid:
                validated_mapping["candidate_rank"] = candidate_index
                validated_mapping["candidate_round"] = round_index
                selected_mapping = validated_mapping
                selected_candidate_rank = candidate_index
                selected_round = round_index
                final_raw_content = generation.raw_content
                final_parsed_payload = generation.parsed_payload
                final_raw_response = generation.raw_response
                candidate_success = True
                break
            else:
                if candidate.get("original"):
                    avoid_substrings.add(str(candidate.get("original")))
                if validation_result.deviation_score < 0.4 or validation_result.semantic_similarity > 0.8:
                    require_option_change = True
                feedback_notes.append(service._build_feedback_note(validated_mapping, validation_result.reasoning))

                if validated_mapping.get("option_change_failed") and available_option_letters:
                    attempted = attempted_target_options.copy()
                    if gold_letter_for_feedback:
                        attempted.add(gold_letter_for_feedback)
                    next_targets = [letter for letter in sorted(available_option_letters) if letter not in attempted]
                    if not next_targets and available_option_letters:
                        # If we exhausted unique letters, cycle through remaining options excluding gold.
                        next_targets = [letter for letter in sorted(available_option_letters) if letter != gold_letter_for_feedback]
                    if next_targets:
                        target_hint = next_targets[0]
                        option_text_hint = None
                        if isinstance(question_model.options_data, dict):
                            for key, value in question_model.options_data.items():
                                letter = service._extract_option_letter(key)
                                if letter == target_hint:
                                    option_text_hint = str(value)
                                    break
                        if option_text_hint:
                            feedback_notes.append(
                                f"Rewrite the stem so option {target_hint} ('{option_text_hint}') becomes correct, while option {gold_letter_for_feedback or 'the current gold option'} is no longer valid."
                            )
                        else:
                            feedback_notes.append(
                                f"Explicitly craft a mapping that makes option {target_hint} the correct answer instead of {gold_letter_for_feedback or 'the current gold option'}."
                            )

        if selected_mapping:
            break
        if not candidate_success and round_index == max_rounds - 1:
            break

    if not selected_mapping:
        raise ValueError("Auto-generated mappings failed validation after multiple attempts")

    preview = final_raw_content or ""
    if len(preview) > 800:
        preview = f"{preview[:800]}…"

    service.logger.info(
        "auto_generate result",
        run_id=run_id,
        question_id=question_model.id,
        provider=provider_used,
        fallback_used=fallback_used,
        mappings_used=1,
        inferred=len([r for r in all_inferred_ranges if r.get("index") == selected_candidate_rank]),
        rejected=len(all_skipped_entries),
        strategy=strategy_used_global,
        reason=final_parsed_payload.get("reason") if isinstance(final_parsed_payload, dict) else None,
        force_refresh=force_refresh,
        raw_preview=preview,
    )

    selected_inferred = [entry for entry in all_inferred_ranges if entry.get("index") == selected_candidate_rank]

    return AutoMappingOutcome(
        prompt=prompt_history[-1] if prompt_history else base_prompt,
        provider=provider_used,
        raw_content=final_raw_content,
        raw_response=final_raw_response,
        parsed_payload=final_parsed_payload,
        enriched_mappings=[selected_mapping],
        inferred_ranges=selected_inferred,
        skipped_entries=all_skipped_entries,
        strategy_used=strategy_used_global,
        fallback_used=fallback_used,
        strategy_validation_focus=strategy_validation_focus,
        attempt_logs=attempt_logs,
        prompt_history=prompt_history,
        selected_candidate_rank=selected_candidate_rank,
        selected_round=selected_round,
        retries_used=max(0, len(prompt_history) - 1),
    )
