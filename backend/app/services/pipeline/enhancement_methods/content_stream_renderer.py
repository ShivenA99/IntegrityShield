from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

import fitz

from .base_renderer import BaseRenderer
from .image_overlay_renderer import ImageOverlayRenderer
from .pymupdf_renderer import PyMuPDFRenderer
from app.utils.storage_paths import method_stage_artifact_path

LOGGER = logging.getLogger(__name__)


class ContentStreamRenderer(BaseRenderer):
    """Rewrites text using PyMuPDF and preserves visuals with image overlays."""

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

        fallback_used = False
        replace_stats: Dict[str, object]
        try:
            rewritten_bytes, rewrite_stats = self.rewrite_content_streams_structured(
                original_bytes,
                clean_mapping,
                mapping_context,
                run_id=run_id,
            )
            replace_stats = {
                "replacements": rewrite_stats.get("replacements", 0),
                "targets": rewrite_stats.get("matches_found", 0),
                "textbox_adjustments": 0,
                "rewritten_bytes": rewritten_bytes,
                "tokens_scanned": rewrite_stats.get("tokens_scanned", 0),
            }
        except Exception as exc:
            LOGGER.warning(
                "structured stream rewrite failed; falling back to PyMuPDF",
                extra={"run_id": run_id, "error": str(exc)},
            )
            fallback_used = True
            renderer = PyMuPDFRenderer()
            doc = fitz.open(stream=original_bytes, filetype="pdf")
            replace_stats = renderer._replace_text(doc, clean_mapping, run_id, mapping_context)
            rewritten_bytes = replace_stats.get("rewritten_bytes") or doc.tobytes()
            doc.close()
            rewrite_stats = {
                "pages": len(replace_stats.get("targets") or []),
                "tj_hits": 0,
                "replacements": replace_stats.get("replacements", 0),
                "matches_found": replace_stats.get("targets", 0),
                "tokens_scanned": 0,
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

        # Step 2: capture overlays from the original document to preserve appearance
        overlay = ImageOverlayRenderer()
        snapshots = overlay._capture_original_snapshots(
            original_bytes,
            clean_mapping,
            run_id=run_id,
            mapping_context=mapping_context,
        )
        fallback_targets = overlay._collect_overlay_targets(
            original_bytes,
            clean_mapping,
            mapping_context=mapping_context,
        )

        # Step 3: apply overlays (image + invisible text layer) on top of rewritten PDF
        doc_overlay = fitz.open(stream=rewritten_bytes, filetype="pdf")
        overlays_applied, total_targets, overlay_area_sum, page_area_sum = overlay._apply_image_snapshots(
            doc_overlay, snapshots, run_id
        )

        if overlays_applied < total_targets and fallback_targets:
            add_applied, add_targets, add_area, add_page_area = overlay._apply_text_overlays_from_rawdict(
                doc_overlay, clean_mapping
            )
            overlays_applied += add_applied
            total_targets += add_targets
            overlay_area_sum += add_area
            page_area_sum += add_page_area

        if overlays_applied == 0:
            question_fallback = overlay._apply_question_fallback_overlays(run_id, doc_overlay)
            if question_fallback:
                overlays_applied += question_fallback
                total_targets += question_fallback

        doc_overlay.save(str(destination))
        doc_overlay.close()
        artifacts["final"] = str(destination)

        try:
            final_bytes = destination.read_bytes()
            self.validate_output_with_context(final_bytes, mapping_context, run_id)
        except Exception as exc:
            LOGGER.error(
                "validation failure after content stream render",
                extra={"run_id": run_id, "error": str(exc)},
            )
            raise

        replacements = int(replace_stats.get("replacements", 0))
        matches = int(replace_stats.get("targets", 0))
        typography_scaled_segments = int(replace_stats.get("textbox_adjustments", 0))
        tokens_scanned = int(replace_stats.get("tokens_scanned", 0))

        effectiveness_score = (
            min(overlays_applied / max(total_targets, 1), 1.0)
            if total_targets
            else (1.0 if replacements else 0.0)
        )
        overlay_area_pct = overlay_area_sum / max(page_area_sum, 1.0) if page_area_sum else 0.0

        rewrite_engine = "structured_stream" if not fallback_used else "pymupdf"

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
                "overlay_applied": overlays_applied,
                "overlay_targets": total_targets,
                "overlay_area_pct": round(overlay_area_pct, 4),
                "artifacts": artifacts,
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
            "overlay_applied": overlays_applied,
            "overlay_targets": total_targets,
            "overlay_area_pct": round(overlay_area_pct, 4),
            "fallback_pages": {"rewrite_engine": rewrite_engine},
            "font_gaps": {},
            "artifacts": artifacts,
        }
