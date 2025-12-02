from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any, Tuple

import fitz

from .base_renderer import BaseRenderer
from .span_rewrite_plan import SpanRewriteEntry
from app.utils.storage_paths import method_stage_artifact_path


class SpanOverlayRenderer(BaseRenderer):
    """Produces span-level stream rewrite output (overlay handled downstream)."""

    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, Any]:
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
                "span_plan_entries": 0,
            }

        mapping_context = self.build_mapping_context(run_id) if run_id else {}
        original_bytes = original_pdf.read_bytes()

        span_plan: Dict[int, List[SpanRewriteEntry]] = {}

        # Generate span plan via structured rewrite (ignoring char-level output)
        _, rewrite_stats = self.rewrite_content_streams_structured(
            original_bytes,
            clean_mapping,
            mapping_context,
            run_id=run_id,
            original_pdf_path=original_pdf,
            span_plan_capture=span_plan,
        )

        span_rewrite_bytes = self.rewrite_spans_only(original_bytes, span_plan)

        overlay_stats = self._apply_span_overlays(
            original_bytes,
            span_rewrite_bytes,
            span_plan,
        )

        destination.write_bytes(overlay_stats["bytes"])

        artifacts: Dict[str, str] = {}
        try:
            span_rewrite_path = method_stage_artifact_path(
                run_id,
                "stream_rewrite_overlay_span",
                "after_span_rewrite",
            )
            span_rewrite_path.write_bytes(overlay_stats["bytes"])
            artifacts["after_span_rewrite"] = str(span_rewrite_path)

            plan_dump_path = method_stage_artifact_path(
                run_id,
                "stream_rewrite_overlay_span",
                "span_plan.json",
            )
            plan_dump_path.write_text(json.dumps(self._serialize_span_plan(span_plan), indent=2))
            artifacts["span_plan"] = str(plan_dump_path)
        except Exception:
            pass

        total_entries = sum(len(v) for v in span_plan.values())

        live_logging_service.emit(
            run_id,
            "pdf_creation",
            "INFO",
            "span overlay rewrite completed",
            component=self.__class__.__name__,
            context={
                "span_plan_entries": total_entries,
                "replacements": rewrite_stats.get("replacements", 0),
                "matches_found": rewrite_stats.get("matches_found", 0),
                "overlays_applied": overlay_stats["overlays_applied"],
                "overlay_area_pct": overlay_stats["overlay_area_pct"],
            },
        )

        return {
            "mapping_entries": len(clean_mapping),
            "file_size_bytes": destination.stat().st_size,
            "effectiveness_score": 1.0 if total_entries else 0.0,
            "replacements": rewrite_stats.get("replacements", 0),
            "matches_found": rewrite_stats.get("matches_found", 0),
            "span_plan_entries": total_entries,
            "overlay_applied": overlay_stats["overlays_applied"],
            "overlay_targets": overlay_stats["overlay_targets"],
            "overlay_area_pct": overlay_stats["overlay_area_pct"],
            "artifacts": artifacts,
            "span_rewrite_plan": self._serialize_span_plan(span_plan),
        }

    def _apply_span_overlays(
        self,
        original_bytes: bytes,
        rewritten_bytes: bytes,
        span_plan: Dict[int, List[SpanRewriteEntry]],
    ) -> Dict[str, Any]:
        doc_original = fitz.open(stream=original_bytes, filetype="pdf")
        doc_rewritten = fitz.open(stream=rewritten_bytes, filetype="pdf")

        overlays_applied = 0
        total_targets = sum(len(entries) for entries in span_plan.values())
        overlay_area_sum = 0.0
        page_area_sum = 0.0

        for page_index, entries in span_plan.items():
            if page_index < 0 or page_index >= len(doc_rewritten):
                continue

            page_rewritten = doc_rewritten[page_index]
            page_area = float(page_rewritten.rect.width * page_rewritten.rect.height) or 1.0

            # Create a temporary single-page document containing the rewritten page so we can
            # embed vector content without resampling artifacts.
            try:
                page_snapshot_doc = fitz.open()
                page_snapshot_doc.insert_pdf(doc_rewritten, from_page=page_index, to_page=page_index)
            except Exception:
                page_snapshot_doc = None

            page_has_overlay = False
            for entry in entries:
                rect = fitz.Rect(entry.bbox)
                if rect.width <= 0 or rect.height <= 0:
                    continue
                if page_snapshot_doc is None:
                    # Fallback to raster overlay if snapshot generation failed
                    try:
                        pix = page_rewritten.get_pixmap(matrix=fitz.Matrix(1, 1), clip=rect, alpha=False)
                        page_rewritten.insert_image(
                            rect,
                            stream=pix.tobytes("png"),
                            keep_proportion=False,
                            overlay=True,
                        )
                        overlays_applied += 1
                        overlay_area_sum += float(rect.width * rect.height)
                        page_has_overlay = True
                    except Exception:
                        continue
                    continue

                try:
                    page_rewritten.show_pdf_page(
                        rect,
                        page_snapshot_doc,
                        0,
                        clip=rect,
                        overlay=True,
                    )
                    overlays_applied += 1
                    overlay_area_sum += float(rect.width * rect.height)
                    page_has_overlay = True
                except Exception:
                    # If vector overlay fails, attempt raster fallback once
                    try:
                        pix = page_rewritten.get_pixmap(matrix=fitz.Matrix(1, 1), clip=rect, alpha=False)
                        page_rewritten.insert_image(
                            rect,
                            stream=pix.tobytes("png"),
                            keep_proportion=False,
                            overlay=True,
                        )
                        overlays_applied += 1
                        overlay_area_sum += float(rect.width * rect.height)
                        page_has_overlay = True
                    except Exception:
                        continue

            if page_has_overlay:
                page_area_sum += page_area

            if page_snapshot_doc is not None:
                page_snapshot_doc.close()

        result_bytes = doc_rewritten.tobytes()
        doc_original.close()
        doc_rewritten.close()

        overlay_area_pct = overlay_area_sum / max(page_area_sum, 1.0) if page_area_sum else 0.0

        return {
            "bytes": result_bytes,
            "overlays_applied": overlays_applied,
            "overlay_targets": total_targets,
            "overlay_area_pct": overlay_area_pct,
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
