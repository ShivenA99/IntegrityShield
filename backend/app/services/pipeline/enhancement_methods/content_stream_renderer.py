from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

from .base_renderer import BaseRenderer
from .span_rewrite_plan import SpanRewriteEntry
from app.utils.storage_paths import method_stage_artifact_path
import fitz
import math
import io

LOGGER = logging.getLogger(__name__)


class ContentStreamRenderer(BaseRenderer):
    """Rewrites text using PyMuPDF with deterministic span-level scaling."""

    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, float | str | int | None]:
        destination.parent.mkdir(parents=True, exist_ok=True)

        from app.services.developer.live_logging_service import live_logging_service

        clean_mapping = {k: v for k, v in (mapping or {}).items() if k and v}
        if not clean_mapping:
            clean_mapping = self.build_mapping_from_questions(run_id)

        if not clean_mapping:
            destination.write_bytes(original_pdf.read_bytes())
            return {
                "mapping_entries": 0,
                "file_size_bytes": destination.stat().st_size,
                "effectiveness_score": 0.0,
                "replacements": 0,
                "matches_found": 0,
            }

        mapping_context = self.build_mapping_context(run_id) if run_id else {}
        original_bytes = original_pdf.read_bytes()

        span_plan: Dict[int, List[SpanRewriteEntry]] = {}

        rewritten_bytes, rewrite_stats = self.rewrite_content_streams_structured(
            original_bytes,
            clean_mapping,
            mapping_context,
            run_id=run_id,
            original_pdf_path=original_pdf,
            span_plan_capture=span_plan,
        )
        replace_stats: Dict[str, object] = {
            "replacements": rewrite_stats.get("replacements", 0),
            "targets": rewrite_stats.get("matches_found", 0),
            "textbox_adjustments": 0,
            "rewritten_bytes": rewritten_bytes,
            "tokens_scanned": rewrite_stats.get("tokens_scanned", 0),
            "span_rewrite_plan": span_plan,
        }

        artifacts: Dict[str, str] = {}
        try:
            if rewritten_bytes:
                rewrite_path = method_stage_artifact_path(
                    run_id,
                    "stream_rewrite-overlay",
                    "after_stream_rewrite",
                )
                rewrite_path.write_bytes(rewritten_bytes)
                artifacts["after_stream_rewrite"] = str(rewrite_path)
        except Exception:
            pass

        fallback_spans: List[SpanRewriteEntry] = []
        total_overlay_spans = 0
        for entries in span_plan.values():
            for entry in entries:
                total_overlay_spans += 1
                if entry.overlay_fallback:
                    fallback_spans.append(entry)

        final_bytes = rewritten_bytes or original_bytes

        overlay_stats = self._overlay_original_spans(
            original_pdf,
            final_bytes,
            span_plan,
        )

        if overlay_stats.get("overlay_bytes"):
            final_bytes = overlay_stats["overlay_bytes"]

        destination.write_bytes(final_bytes)
        artifacts["final"] = str(destination)

        replacements = int(replace_stats.get("replacements", 0))
        matches = int(replace_stats.get("targets", 0))
        typography_scaled_segments = int(replace_stats.get("textbox_adjustments", 0))
        tokens_scanned = int(replace_stats.get("tokens_scanned", 0))

        scaled_spans = sum(
            1
            for entries in span_plan.values()
            for entry in entries
            if entry.requires_scaling or (entry.scale_factor and abs(entry.scale_factor - 1.0) > 1e-3)
        )

        effectiveness_score = 1.0 if replacements else 0.0

        rewrite_engine = "courier_font_strategy"

        serialized_plan = self._serialize_span_plan(span_plan)
        plan_summary = {
            "pages": len(serialized_plan),
            "entries": sum(len(entries) for entries in serialized_plan.values()),
            "scaled_entries": sum(
                1
                for entries in span_plan.values()
                for entry in entries
                if entry.requires_scaling or (entry.scale_factor and abs(entry.scale_factor - 1.0) > 1e-3)
            ),
        }

        if serialized_plan:
            try:
                plan_path = method_stage_artifact_path(
                    run_id,
                    "stream_rewrite-overlay",
                    "span_plan.json",
                )
                plan_path.write_text(json.dumps(serialized_plan, indent=2))
                artifacts["span_plan"] = str(plan_path)
            except Exception:
                pass

        live_logging_service.emit(
            run_id,
            "pdf_creation",
            "INFO",
            "content_stream rendering completed",
            component=self.__class__.__name__,
            context={
                "replacements": replacements,
                "matches_found": matches,
                "tokens_scanned": tokens_scanned,
                "typography_scaled_segments": typography_scaled_segments,
                "fallback_pages": {"rewrite_engine": rewrite_engine},
                "scaled_spans": scaled_spans,
                "span_plan_summary": plan_summary,
                "artifacts": artifacts,
                "overlay_fallback_spans": len(fallback_spans),
                "overlay_total_spans": total_overlay_spans,
            },
        )

        return {
            "mapping_entries": len(clean_mapping),
            "file_size_bytes": destination.stat().st_size,
            "effectiveness_score": effectiveness_score,
            "replacements": replacements,
            "matches_found": matches,
            "tokens_scanned": tokens_scanned,
            "typography_scaled_segments": typography_scaled_segments,
            "overlay_applied": overlay_stats.get("overlay_count", 0),
            "overlay_targets": overlay_stats.get("overlay_count", 0),
            "overlay_area_pct": overlay_stats.get("overlay_area_pct", 0.0),
            "fallback_pages": {"rewrite_engine": rewrite_engine},
            "font_gaps": {},
            "artifacts": artifacts,
            "scaled_spans": scaled_spans,
            "span_plan": serialized_plan,
            "span_plan_summary": plan_summary,
        }

    def _serialize_span_plan(
        self,
        span_plan: Dict[int, List[SpanRewriteEntry]],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for page_index, entries in span_plan.items():
            serialized_entries: List[Dict[str, Any]] = []
            for entry in entries:
                serialized_entries.append(
                    {
                        "page_index": entry.page_index,
                        "block_index": entry.block_index,
                        "line_index": entry.line_index,
                        "span_index": entry.span_index,
                        "operator_index": entry.operator_index,
                        "original_text": entry.original_text,
                        "replacement_text": entry.replacement_text,
                        "font": entry.font,
                        "font_size": entry.font_size,
                        "bbox": entry.bbox,
                        "matrix": entry.matrix,
                        "original_width": entry.original_width,
                        "replacement_width": entry.replacement_width,
                        "scale_factor": entry.scale_factor,
                        "overlay_fallback": entry.overlay_fallback,
                        "requires_scaling": entry.requires_scaling,
                        "slice_replacements": entry.slice_replacements,
                        "fragment_rewrites": [
                            {
                                "index": fragment.index,
                                "original_text": fragment.original_text,
                                "replacement_text": fragment.replacement_text,
                                "literal_kind": fragment.literal_kind,
                                "preserved_literal": fragment.preserved_literal,
                            }
                            for fragment in entry.fragment_rewrites
                        ],
                        "mappings": [
                            {
                                "q_number": ref.q_number,
                                "original": ref.original,
                                "replacement": ref.replacement,
                                "context_index": ref.context_index,
                                "start": ref.start,
                                "end": ref.end,
                                "operator_index": ref.operator_index,
                            }
                            for ref in entry.mappings
                        ],
                        "validation_failures": entry.validation_failures,
                    }
                )
            result[str(page_index)] = serialized_entries
        return result

    def _overlay_original_spans(
        self,
        original_pdf: Path,
        rewritten_bytes: bytes,
        span_plan: Dict[int, List[SpanRewriteEntry]],
        ) -> Dict[str, Any]:
        if not rewritten_bytes or not span_plan:
            return {"overlay_count": 0, "overlay_area_pct": 0.0}

        try:
            original_bytes = original_pdf.read_bytes()
        except Exception:
            return {"overlay_count": 0, "overlay_area_pct": 0.0}

        try:
            source_doc = fitz.open(stream=original_bytes, filetype="pdf")
        except Exception:
            return {"overlay_count": 0, "overlay_area_pct": 0.0}

        try:
            target_doc = fitz.open(stream=rewritten_bytes, filetype="pdf")
        except Exception:
            source_doc.close()
            return {"overlay_count": 0, "overlay_area_pct": 0.0}

        overlay_count = 0
        overlay_area = 0.0
        page_area_total = 0.0

        try:
            source_raw_cache: Dict[int, Dict[str, Any]] = {}
            for page_index, entries in span_plan.items():
                if not entries:
                    continue
                if page_index >= len(source_doc) or page_index >= len(target_doc):
                    continue

                source_page = source_doc[page_index]
                target_page = target_doc[page_index]
                page_area_total += abs(target_page.rect.width * target_page.rect.height)

                source_raw = source_raw_cache.get(page_index)
                if source_raw is None:
                    try:
                        source_raw = source_page.get_text("rawdict") or {}
                    except Exception:
                        source_raw = {}
                    source_raw_cache[page_index] = source_raw

                source_blocks = source_raw.get("blocks") or []

                line_rects: Dict[Tuple[int, int], fitz.Rect] = {}
                for block_idx, block in enumerate(source_blocks):
                    for line_idx, line in enumerate(block.get("lines", [])):
                        rect = self._derive_line_rect(line)
                        if rect is None:
                            continue
                        if rect.is_empty or rect.width <= 0 or rect.height <= 0:
                            continue
                        line_rects[(block_idx, line_idx)] = rect

                processed_lines: Set[Tuple[int, int]] = set()

                for entry in entries:
                    block_idx = int(entry.block_index) if entry.block_index is not None else None
                    line_idx = int(entry.line_index) if entry.line_index is not None else None
                    if block_idx is None or line_idx is None:
                        continue

                    line_key = (block_idx, line_idx)
                    if line_key in processed_lines:
                        continue

                    rect = line_rects.get(line_key)
                    if rect is None:
                        bbox = entry.bbox
                        if bbox and len(bbox) == 4:
                            try:
                                rect = fitz.Rect(bbox)
                            except Exception:
                                rect = None
                    if rect is None or rect.is_empty or rect.width <= 0 or rect.height <= 0:
                        continue

                    try:
                        clip_rect = fitz.Rect(rect)
                        zoom = fitz.Matrix(3, 3)
                        pix = source_page.get_pixmap(matrix=zoom, clip=clip_rect, alpha=False)
                    except Exception:
                        continue

                    try:
                        target_page.insert_image(
                            rect,
                            pixmap=pix,
                            overlay=True,
                            keep_proportion=False,
                        )
                    except Exception:
                        continue

                    processed_lines.add(line_key)
                    overlay_count += 1
                    overlay_area += abs(rect.width * rect.height)

            buffer = io.BytesIO()
            target_doc.save(buffer)
            overlay_bytes = buffer.getvalue()
        except Exception:
            overlay_bytes = None
        finally:
            source_doc.close()
            target_doc.close()

        area_pct = 0.0
        if overlay_area and page_area_total:
            area_pct = min(100.0, (overlay_area / page_area_total) * 100.0)

        result: Dict[str, Any] = {
            "overlay_count": overlay_count,
            "overlay_area_pct": area_pct,
        }
        if overlay_bytes:
            result["overlay_bytes"] = overlay_bytes
        return result

    def _derive_line_rect(self, line: Dict[str, Any]) -> Optional[fitz.Rect]:
        rect: Optional[fitz.Rect] = None
        for span in line.get("spans", []):
            span_rect = self._derive_span_rect(span)
            if span_rect is None:
                continue
            rect = span_rect if rect is None else rect | span_rect
        return rect

    def _derive_span_rect(self, span: Dict[str, Any]) -> Optional[fitz.Rect]:
        chars = span.get("chars") or []
        boxes: List[fitz.Rect] = []
        for details in chars:
            bbox = details.get("bbox") if isinstance(details, dict) else None
            if not bbox:
                continue
            try:
                boxes.append(fitz.Rect(bbox))
            except Exception:
                continue

        if boxes:
            aggregated = boxes[0]
            for box in boxes[1:]:
                aggregated |= box
            return aggregated

        bbox = span.get("bbox")
        if bbox:
            try:
                return fitz.Rect(bbox)
            except Exception:
                return None

        return None
