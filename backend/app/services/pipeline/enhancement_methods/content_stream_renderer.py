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

        # Step 1: perform text rewrites with PyMuPDF so underlying content matches the mapping
        renderer = PyMuPDFRenderer()
        mapping_context = self.build_mapping_context(run_id) if run_id else {}
        doc = fitz.open(str(original_pdf))
        replace_stats = renderer._replace_text(doc, clean_mapping, run_id, mapping_context)
        rewritten_bytes = replace_stats.get("rewritten_bytes") or doc.tobytes()
        doc.close()

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
        original_bytes = original_pdf.read_bytes()
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

        replacements = replace_stats["replacements"]
        matches = replace_stats["targets"]
        typography_scaled_segments = replace_stats["textbox_adjustments"]

        effectiveness_score = (
            min(overlays_applied / max(total_targets, 1), 1.0)
            if total_targets
            else (1.0 if replacements else 0.0)
        )
        overlay_area_pct = overlay_area_sum / max(page_area_sum, 1.0) if page_area_sum else 0.0

        live_logging_service.emit(
            run_id,
            "pdf_creation",
            "INFO",
            "content_stream rendering completed",
            component=self.__class__.__name__,
            context={
                "replacements": replacements,
                "matches_found": matches,
                "tokens_scanned": 0,
                "typography_scaled_segments": typography_scaled_segments,
                "fallback_pages": {"rewrite_engine": "pymupdf"},
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
            "tokens_scanned": 0,
            "typography_scaled_segments": typography_scaled_segments,
            "overlay_applied": overlays_applied,
            "overlay_targets": total_targets,
            "overlay_area_pct": round(overlay_area_pct, 4),
            "fallback_pages": {"rewrite_engine": "pymupdf"},
            "font_gaps": {},
            "artifacts": artifacts,
        }
