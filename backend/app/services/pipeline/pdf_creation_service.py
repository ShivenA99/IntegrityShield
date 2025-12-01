from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List

from flask import current_app

from ...extensions import db
from ...models import EnhancedPDF, PipelineRun, QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from ...utils.storage_paths import enhanced_pdf_path, run_directory
from .enhancement_methods import RENDERERS
from .enhancement_methods.base_renderer import BaseRenderer


class PdfCreationService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        # Ensure we can read/write structured.json
        self.structured_manager = StructuredDataManager()

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        return self._generate_pdfs(run_id)

    def _collect_question_mapping_gaps(
        self,
        questions: List[QuestionManipulation],
    ) -> List[Dict[str, Any]]:
        missing: List[Dict[str, Any]] = []
        for q in questions:
            q_label = str(q.question_number or q.id)
            mappings = q.substring_mappings or []
            if not mappings:
                missing.append({"question": q_label, "reason": "no_mappings"})
                continue
            if not any(bool(mapping.get("validated")) for mapping in mappings):
                missing.append({"question": q_label, "reason": "no_validated_mappings"})
        return missing

    def _resolve_base_pdf(self, run: PipelineRun) -> Path:
        structured = self.structured_manager.load(run.id) or {}
        document_meta = structured.get("document") or {}
        pipeline_meta = structured.get("pipeline_metadata") or {}
        extraction_outputs = (pipeline_meta.get("data_extraction_outputs") or {}) if isinstance(pipeline_meta, dict) else {}

        candidates = [
            document_meta.get("reconstructed_path"),
            document_meta.get("pdf"),
            extraction_outputs.get("pdf"),
            document_meta.get("source_path"),
            run.original_pdf_path,
        ]

        for candidate in candidates:
            if not candidate:
                continue
            candidate_path = Path(str(candidate))
            if candidate_path.exists():
                if str(candidate_path) != run.original_pdf_path:
                    self.logger.info(
                        "pdf_creation base PDF resolved",
                        extra={"run_id": run.id, "path": str(candidate_path)},
                    )
                return candidate_path

        fallback = Path(run.original_pdf_path)
        if not fallback.exists():
            self.logger.warning(
                "pdf_creation base PDF fallback missing on disk",
                extra={"run_id": run.id, "path": run.original_pdf_path},
            )
        return fallback

    def _prepare_methods_if_missing(self, run: PipelineRun) -> None:
        """Ensure EnhancedPDF rows exist for configured methods so pdf_creation can render.
        If some exist, add any missing ones (always include image_overlay).
        """
        from ..developer.live_logging_service import live_logging_service
        from .enhancement_methods.base_renderer import BaseRenderer

        configured = run.pipeline_config.get("enhancement_methods") or [
            "latex_dual_layer",
        ]

        # In prevention mode, don't add latex_dual_layer (it requires validated mappings)
        mode = run.pipeline_config.get("mode")
        if mode != "prevention":
            if "latex_dual_layer" not in configured:
                configured.insert(0, "latex_dual_layer")

        # Deduplicate while preserving order
        seen = set()
        configured = [m for m in configured if not (m in seen or seen.add(m))]

        existing_records = EnhancedPDF.query.filter_by(pipeline_run_id=run.id).all()
        existing_methods = {rec.method_name for rec in existing_records}

        methods_to_add = [m for m in configured if m not in existing_methods]
        if not methods_to_add:
            return

        for method in methods_to_add:
            pdf_path = enhanced_pdf_path(run.id, method)
            enhanced = EnhancedPDF(
                pipeline_run_id=run.id,
                method_name=method,
                file_path=str(pdf_path),
                generation_config={"method": method},
            )
            db.session.add(enhanced)
        db.session.commit()

        live_logging_service.emit(
            run.id,
            "pdf_creation",
            "INFO",
            "auto-prepared enhancement methods for pdf_creation",
            context={"methods": configured, "added": methods_to_add},
        )

    def _audit_geometry_mappings(
        self,
        run_id: str,
        questions: list[QuestionManipulation],
        base_renderer,
    ) -> Dict[str, Any]:
        from ..developer.live_logging_service import live_logging_service

        structured = self.structured_manager.load(run_id) or {}
        span_index_data = structured.get("pymupdf_span_index") or []
        span_lookup: Dict[str, Dict[str, Any]] = {}
        for entry in span_index_data:
            spans = entry.get("spans") or []
            for span in spans:
                span_id = str(span.get("id"))
                if span_id:
                    span_lookup[span_id] = span

        audited = 0
        issues: List[Dict[str, Any]] = []

        for question in questions:
            q_label = str(question.question_number or question.id)
            mappings = list(question.substring_mappings or [])
            for mapping in mappings:
                original = base_renderer.strip_zero_width(
                    str(mapping.get("original") or "")
                ).strip()
                replacement = base_renderer.strip_zero_width(
                    str(mapping.get("replacement") or "")
                ).strip()
                if not original:
                    continue

                span_ids = list(
                    mapping.get("selection_span_ids") or mapping.get("span_ids") or []
                )
                if not span_ids:
                    continue

                combined_text = base_renderer._collect_span_text(span_lookup, span_ids)
                normalized_span = base_renderer._normalize_for_compare(combined_text)
                normalized_original = base_renderer._normalize_for_compare(original)
                normalized_replacement = (
                    base_renderer._normalize_for_compare(replacement)
                    if replacement
                    else ""
                )

                audited += 1

                contains_original = (
                    bool(normalized_original) and normalized_original in normalized_span
                )
                replacement_collides = (
                    bool(normalized_replacement)
                    and normalized_replacement in normalized_span
                )

                if not contains_original or (
                    replacement_collides
                    and normalized_replacement != normalized_original
                ):
                    issues.append(
                        {
                            "question": q_label,
                            "mapping_id": mapping.get("id"),
                            "span_ids": span_ids,
                            "contains_original": contains_original,
                            "replacement_overlap": replacement_collides,
                        }
                    )

        summary = {
            "audited_mappings": audited,
            "issue_count": len(issues),
            "issues": issues[:10],
        }

        level = "WARNING" if issues else "INFO"
        live_logging_service.emit(
            run_id,
            "pdf_creation",
            level,
            "geometry audit completed",
            component="geometry_audit",
            context={
                "audited_mappings": audited,
                "issues": len(issues),
                "highlighted": issues[:3],
            },
        )

        return summary

    def _generate_pdfs(self, run_id: str) -> Dict[str, Any]:
        from ..developer.live_logging_service import live_logging_service

        run = PipelineRun.query.get(run_id)
        if not run:
            raise ValueError("Pipeline run not found")

        questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
        total_q = len(questions)
        with_map = sum(1 for q in questions if q.substring_mappings)
        with_validated = sum(
            1
            for q in questions
            if any(
                bool(mapping.get("validated"))
                for mapping in (q.substring_mappings or [])
            )
        )
        mapping_gaps = self._collect_question_mapping_gaps(questions)
        live_logging_service.emit(
            run_id,
            "pdf_creation",
            "INFO",
            "pdf_creation gating check",
            context={
                "total_questions": total_q,
                "with_mappings": with_map,
                "with_validated": with_validated,
                "skipped_questions": mapping_gaps[:5],
            },
        )
        if mapping_gaps:
            live_logging_service.emit(
                run_id,
                "pdf_creation",
                "WARNING",
                "Proceeding with pdf_creation despite missing/invalid mappings",
                context={"skipped_count": len(mapping_gaps)},
            )

        base_renderer = BaseRenderer()
        audit_summary = self._audit_geometry_mappings(run_id, questions, base_renderer)

        # Ensure we have EnhancedPDF rows; add any missing methods
        self._prepare_methods_if_missing(run)

        run_dir = run_directory(run_id).resolve()
        original_pdf = self._resolve_base_pdf(run)
        enhanced_records = EnhancedPDF.query.filter_by(pipeline_run_id=run_id).all()

        results: Dict[str, Any] = {"skipped_questions": mapping_gaps}
        debug_capture: Dict[str, Any] = {}
        performance_metrics: Dict[str, Any] = {}

        # Phase 5: Comprehensive instrumentation - start timing
        overall_start_time = time.time()

        # Build enhanced mapping once with discovered tokens for dual-layer coordination
        mapping_start_time = time.time()
        with original_pdf.open("rb") as f:
            pdf_bytes = f.read()

        # Use a base renderer instance to get enhanced mapping
        enhanced_mapping, discovered_tokens = (
            base_renderer.build_enhanced_mapping_with_discovery(run_id, pdf_bytes)
        )
        mapping_build_time = time.time() - mapping_start_time

        # Calculate enhancement statistics
        base_mapping = base_renderer.build_mapping_from_questions(run_id)
        enhancement_stats = {
            "base_mapping_size": len(base_mapping),
            "enhanced_mapping_size": len(enhanced_mapping),
            "discovered_tokens_count": len(discovered_tokens),
            "enhancement_ratio": len(enhanced_mapping) / max(len(base_mapping), 1),
            "discovery_coverage": len(discovered_tokens)
            / max(len(enhanced_mapping), 1),
        }

        live_logging_service.emit(
            run_id,
            "pdf_creation",
            "INFO",
            "dual-layer coordination: enhanced mapping prepared",
            context={
                **enhancement_stats,
                "renderer_methods": [r.method_name for r in enhanced_records],
                "mapping_build_time_ms": round(mapping_build_time * 1000, 2),
                "original_pdf_size_bytes": len(pdf_bytes),
            },
        )

        # Phase 4: Dual-layer architecture - process in optimal order
        # Stream layer first (content_stream), then visual layer (image_overlay)
        stream_first_methods = {
            "content_stream_overlay",
            "content_stream",
            "content_stream_span_overlay",
        }
        overlay_methods = {
            "image_overlay",
            "latex_dual_layer",
            "latex_font_attack",
            "latex_icw",
            "latex_icw_dual_layer",
            "latex_icw_font_attack",
        }
        pymupdf_methods = {"pymupdf_overlay"}

        content_stream_records = [
            r for r in enhanced_records if r.method_name in stream_first_methods
        ]
        pymupdf_records = [
            r for r in enhanced_records if r.method_name in pymupdf_methods
        ]
        image_overlay_records = [
            r for r in enhanced_records if r.method_name in overlay_methods
        ]
        other_records = [
            r
            for r in enhanced_records
            if r.method_name
            not in stream_first_methods | overlay_methods | pymupdf_methods
        ]

        # Process in coordinated order for dual-layer architecture
        ordered_records = (
            content_stream_records
            + pymupdf_records
            + image_overlay_records
            + other_records
        )

        app = current_app._get_current_object()

        for record in ordered_records:
            destination = Path(record.file_path)
            renderer_cls = RENDERERS.get(record.method_name)
            if not renderer_cls:
                continue

            renderer = renderer_cls()
            renderer_start_time = time.time()

            live_logging_service.emit(
                run_id,
                "pdf_creation",
                "INFO",
                f"dual-layer: starting {record.method_name} renderer",
                context={
                    "enhanced_mapping_entries": len(enhanced_mapping),
                    "layer_type": (
                        "stream"
                        if record.method_name in stream_first_methods
                        else (
                            "visual"
                            if record.method_name in overlay_methods | pymupdf_methods
                            else "other"
                        )
                    ),
                },
                component=record.method_name,
            )

            # Pass the enhanced mapping to the renderer (renderers now handle enhancement internally)
            try:
                with app.app_context():
                    metadata = renderer.render(
                        run_id, original_pdf, destination, enhanced_mapping
                    )
                render_success = True
                render_error = None
            except Exception as e:
                metadata = {
                    "error": str(e),
                    "file_size_bytes": 0,
                    "effectiveness_score": 0.0,
                }
                render_success = False
                render_error = str(e)
                self.logger.exception(
                    "Renderer execution failed",
                    extra={
                        "run_id": run_id,
                        "method": record.method_name,
                    },
                )
                live_logging_service.emit(
                    run_id,
                    "pdf_creation",
                    "ERROR",
                    f"dual-layer: {record.method_name} renderer failed",
                    context={"error": str(e)},
                    component=record.method_name,
                )

            renderer_duration = time.time() - renderer_start_time
            span_plan_for_results = metadata.get("span_plan")
            span_plan_summary = metadata.get("span_plan_summary")
            performance_metrics[record.method_name] = {
                "duration_ms": round(renderer_duration * 1000, 2),
                "success": render_success,
                "error": render_error,
                "output_size_bytes": metadata.get("file_size_bytes", 0),
            }

            # Capture debug information
            if record.method_name in stream_first_methods:
                debug_capture[record.method_name] = {
                    "enhanced_mapping_stats": {
                        "total_entries": len(enhanced_mapping),
                        "discovered_tokens": len(discovered_tokens),
                    },
                    "span_plan_summary": span_plan_summary,
                    "scaled_spans": metadata.get("scaled_spans"),
                    "span_plan_path": metadata.get("artifact_rel_paths", {}).get(
                        "span_plan"
                    ),
                    "span_plan": span_plan_for_results,
                }
            elif record.method_name in overlay_methods | pymupdf_methods:
                debug_capture.setdefault("overlay_layers", {})[record.method_name] = {
                    "effectiveness_score": metadata.get("effectiveness_score"),
                    "mapping_entries_used": metadata.get("mapping_entries"),
                    "enhanced_mapping_boost": len(enhanced_mapping)
                    - len(base_renderer.build_mapping_from_questions(run_id)),
                }

            record.file_size_bytes = int(
                metadata.get("file_size_bytes")
                or (destination.stat().st_size if destination.exists() else 0)
            )
            trimmed_stats = dict(metadata)
            if span_plan_for_results is not None:
                trimmed_stats.pop("span_plan", None)
            record.effectiveness_stats = trimmed_stats
            record.visual_quality_score = (
                0.97 if record.method_name == "dual_layer" else 0.92
            )
            db.session.add(record)

            results[record.method_name] = metadata

            artifacts = metadata.get("artifacts") or {}
            if artifacts:
                artifact_rel_paths: Dict[str, str] = {}
                for stage_name, artifact_path in artifacts.items():
                    try:
                        rel = str(Path(artifact_path).resolve().relative_to(run_dir))
                        artifact_rel_paths[stage_name] = rel
                    except Exception:
                        continue
                if artifact_rel_paths:
                    metadata["artifact_rel_paths"] = artifact_rel_paths

        results["geometry_audit"] = audit_summary

        db.session.commit()

        structured = self.structured_manager.load(run_id)
        manipulation_results = structured.setdefault("manipulation_results", {})
        manipulation_results.setdefault("enhanced_pdfs", {})
        manipulation_results["skipped_questions"] = mapping_gaps
        manipulation_results["geometry_audit"] = audit_summary
        artifact_map = manipulation_results.setdefault("artifacts", {})
        for record in enhanced_records:
            stats = record.effectiveness_stats or {}
            try:
                relative_path = str(
                    Path(record.file_path).resolve().relative_to(run_dir)
                )
            except Exception:
                relative_path = None
            # Provide both legacy (path, size_bytes) and explicit (file_path, file_size_bytes) keys for UI compatibility
            manipulation_results["enhanced_pdfs"][record.method_name] = {
                "path": record.file_path,
                "size_bytes": record.file_size_bytes,
                "file_path": record.file_path,
                "relative_path": relative_path,
                "file_size_bytes": record.file_size_bytes,
                "visual_quality_score": record.visual_quality_score,
                "effectiveness_score": stats.get("effectiveness_score"),
                "scaled_spans": stats.get("scaled_spans"),
                "span_plan_summary": stats.get("span_plan_summary"),
                "render_stats": stats,
                "created_at": isoformat(utc_now()),
            }
            artifact_map[record.method_name] = stats.get(
                "artifact_rel_paths", {}
            ) or stats.get("artifacts", {})
        # Phase 5: Comprehensive instrumentation - calculate final metrics
        overall_duration = time.time() - overall_start_time
        total_output_size = sum(
            m.get("output_size_bytes", 0) for m in performance_metrics.values()
        )
        successful_renderers = sum(
            1 for m in performance_metrics.values() if m.get("success", False)
        )
        failed_renderers = len(performance_metrics) - successful_renderers

        comprehensive_metrics = {
            "overall_duration_ms": round(overall_duration * 1000, 2),
            "mapping_build_time_ms": round(mapping_build_time * 1000, 2),
            "enhancement_stats": enhancement_stats,
            "performance_metrics": performance_metrics,
            "success_summary": {
                "successful_renderers": successful_renderers,
                "failed_renderers": failed_renderers,
                "success_rate": successful_renderers / max(len(performance_metrics), 1),
            },
            "size_metrics": {
                "original_pdf_size_bytes": len(pdf_bytes),
                "total_output_size_bytes": total_output_size,
                "size_efficiency": total_output_size / max(len(pdf_bytes), 1),
            },
        }

        if debug_capture:
            structured.setdefault("manipulation_results", {}).setdefault(
                "debug", {}
            ).update(debug_capture)

        # Store comprehensive metrics in structured data
        structured.setdefault("manipulation_results", {}).setdefault(
            "comprehensive_metrics", {}
        ).update(comprehensive_metrics)
        self.structured_manager.save(run_id, structured)

        live_logging_service.emit(
            run_id,
            "pdf_creation",
            "INFO",
            "dual-layer PDF creation completed with comprehensive instrumentation",
            context={
                "methods": list(results.keys()),
                "results": results,
                **comprehensive_metrics,
                "dual_layer_architecture": {
                    "stream_layer": any(
                        key in results
                        for key in (
                            "content_stream_overlay",
                            "content_stream",
                            "content_stream_span_overlay",
                        )
                    ),
                    "visual_layer": any(
                        key in results for key in ("pymupdf_overlay", "image_overlay")
                    ),
                    "coordination_successful": failed_renderers == 0,
                },
            },
        )
        # Auto-report generation moved to results_generation_service to avoid timing conflicts
        return {
            "enhanced_count": len(enhanced_records),
            "methods": [r.method_name for r in enhanced_records],
        }
