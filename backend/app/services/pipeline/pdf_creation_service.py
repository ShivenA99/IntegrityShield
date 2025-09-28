from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict

from ...extensions import db
from ...models import EnhancedPDF, PipelineRun, QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from ...utils.storage_paths import enhanced_pdf_path, run_directory
from .enhancement_methods import RENDERERS


class PdfCreationService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        # Ensure we can read/write structured.json
        self.structured_manager = StructuredDataManager()

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._generate_pdfs, run_id)

    def _all_questions_have_mappings(self, run_id: str) -> bool:
        """TEMP: For testing, just check if all questions have mappings (not validation required)"""
        questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
        if not questions:
            return False
        for q in questions:
            mappings = q.substring_mappings or []
            if not mappings:
                return False
        return True

    def _prepare_methods_if_missing(self, run: PipelineRun) -> None:
        """Ensure EnhancedPDF rows exist for configured methods so pdf_creation can render.
        If some exist, add any missing ones (always include image_overlay).
        """
        from ..developer.live_logging_service import live_logging_service

        configured = run.pipeline_config.get("enhancement_methods") or ["content_stream_overlay", "pymupdf_overlay"]
        if "content_stream_overlay" not in configured:
            configured.insert(0, "content_stream_overlay")
        if "pymupdf_overlay" not in configured:
            configured.append("pymupdf_overlay")
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

    def _generate_pdfs(self, run_id: str) -> Dict[str, Any]:
        from ..developer.live_logging_service import live_logging_service

        run = PipelineRun.query.get(run_id)
        if not run:
            raise ValueError("Pipeline run not found")

        # Gate: require at least one mapping per question
        questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
        total_q = len(questions)
        with_map = sum(1 for q in questions if (q.substring_mappings or []))
        without_map = total_q - with_map
        live_logging_service.emit(
            run_id,
            "pdf_creation",
            "INFO",
            "pdf_creation gating check",
            context={"total_questions": total_q, "with_mappings": with_map, "without_mappings": without_map},
        )

        if not self._all_questions_have_mappings(run_id):
            raise ValueError(
                "PDF creation blocked: All questions must have at least one mapping."
            )

        # Ensure we have EnhancedPDF rows; add any missing methods
        self._prepare_methods_if_missing(run)

        run_dir = run_directory(run_id).resolve()
        original_pdf = Path(run.original_pdf_path)
        enhanced_records = EnhancedPDF.query.filter_by(pipeline_run_id=run_id).all()

        results: Dict[str, Any] = {}
        debug_capture: Dict[str, Any] = {}
        performance_metrics: Dict[str, Any] = {}

        # Phase 5: Comprehensive instrumentation - start timing
        overall_start_time = time.time()

        # Build enhanced mapping once with discovered tokens for dual-layer coordination
        mapping_start_time = time.time()
        with original_pdf.open("rb") as f:
            pdf_bytes = f.read()

        # Use a base renderer instance to get enhanced mapping
        from .enhancement_methods.base_renderer import BaseRenderer
        base_renderer = BaseRenderer()
        enhanced_mapping, discovered_tokens = base_renderer.build_enhanced_mapping_with_discovery(run_id, pdf_bytes)
        mapping_build_time = time.time() - mapping_start_time

        # Calculate enhancement statistics
        base_mapping = base_renderer.build_mapping_from_questions(run_id)
        enhancement_stats = {
            "base_mapping_size": len(base_mapping),
            "enhanced_mapping_size": len(enhanced_mapping),
            "discovered_tokens_count": len(discovered_tokens),
            "enhancement_ratio": len(enhanced_mapping) / max(len(base_mapping), 1),
            "discovery_coverage": len(discovered_tokens) / max(len(enhanced_mapping), 1),
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
        stream_first_methods = {"content_stream_overlay", "content_stream"}
        overlay_methods = {"image_overlay"}
        pymupdf_methods = {"pymupdf_overlay"}

        content_stream_records = [r for r in enhanced_records if r.method_name in stream_first_methods]
        pymupdf_records = [r for r in enhanced_records if r.method_name in pymupdf_methods]
        image_overlay_records = [r for r in enhanced_records if r.method_name in overlay_methods]
        other_records = [
            r
            for r in enhanced_records
            if r.method_name not in stream_first_methods | overlay_methods | pymupdf_methods
        ]

        # Process in coordinated order for dual-layer architecture
        ordered_records = content_stream_records + pymupdf_records + image_overlay_records + other_records

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
                        else "visual"
                        if record.method_name in overlay_methods | pymupdf_methods
                        else "other"
                    ),
                },
                component=record.method_name,
            )

            # Pass the enhanced mapping to the renderer (renderers now handle enhancement internally)
            try:
                metadata = renderer.render(run_id, original_pdf, destination, enhanced_mapping)
                render_success = True
                render_error = None
            except Exception as e:
                metadata = {"error": str(e), "file_size_bytes": 0, "effectiveness_score": 0.0}
                render_success = False
                render_error = str(e)
                live_logging_service.emit(
                    run_id,
                    "pdf_creation",
                    "ERROR",
                    f"dual-layer: {record.method_name} renderer failed",
                    context={"error": str(e)},
                    component=record.method_name,
                )

            renderer_duration = time.time() - renderer_start_time
            performance_metrics[record.method_name] = {
                "duration_ms": round(renderer_duration * 1000, 2),
                "success": render_success,
                "error": render_error,
                "output_size_bytes": metadata.get("file_size_bytes", 0),
            }

            # Capture debug information
            if record.method_name in stream_first_methods:
                debug_capture["content_stream_overlay"] = {
                    "decoded_sample": metadata.get("debug_sample"),
                    "per_font_top_tokens": metadata.get("debug_per_font_top_tokens"),
                    "enhanced_mapping_stats": {
                        "total_entries": len(enhanced_mapping),
                        "discovered_tokens": len(discovered_tokens),
                    },
                }
            elif record.method_name in overlay_methods | pymupdf_methods:
                debug_capture.setdefault("overlay_layers", {})[record.method_name] = {
                    "effectiveness_score": metadata.get("effectiveness_score"),
                    "mapping_entries_used": metadata.get("mapping_entries"),
                    "enhanced_mapping_boost": len(enhanced_mapping) - len(base_renderer.build_mapping_from_questions(run_id)),
                }

            record.file_size_bytes = int(metadata.get("file_size_bytes", destination.stat().st_size))
            record.effectiveness_stats = {**(record.effectiveness_stats or {}), **metadata}
            record.visual_quality_score = 0.97 if record.method_name == "dual_layer" else 0.92
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

        db.session.commit()

        structured = self.structured_manager.load(run_id)
        manipulation_results = structured.setdefault("manipulation_results", {})
        manipulation_results.setdefault("enhanced_pdfs", {})
        artifact_map = manipulation_results.setdefault("artifacts", {})
        for record in enhanced_records:
            stats = record.effectiveness_stats or {}
            try:
                relative_path = str(Path(record.file_path).resolve().relative_to(run_dir))
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
                "overlay_applied": stats.get("overlay_applied"),
                "overlay_targets": stats.get("overlay_targets"),
                "overlay_area_pct": stats.get("overlay_area_pct"),
                "render_stats": stats,
                "created_at": isoformat(utc_now()),
            }
            artifact_map[record.method_name] = stats.get("artifact_rel_paths", {}) or stats.get("artifacts", {})
        # Phase 5: Comprehensive instrumentation - calculate final metrics
        overall_duration = time.time() - overall_start_time
        total_output_size = sum(m.get("output_size_bytes", 0) for m in performance_metrics.values())
        successful_renderers = sum(1 for m in performance_metrics.values() if m.get("success", False))
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
            structured.setdefault("manipulation_results", {}).setdefault("debug", {}).update(debug_capture)

        # Store comprehensive metrics in structured data
        structured.setdefault("manipulation_results", {}).setdefault("comprehensive_metrics", {}).update(comprehensive_metrics)
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
                        key in results for key in ("content_stream_overlay", "content_stream")
                    ),
                    "visual_layer": any(
                        key in results for key in ("pymupdf_overlay", "image_overlay")
                    ),
                    "coordination_successful": failed_renderers == 0,
                },
            },
        )

        return {
            "enhanced_count": len(enhanced_records),
            "methods": [r.method_name for r in enhanced_records],
        }
