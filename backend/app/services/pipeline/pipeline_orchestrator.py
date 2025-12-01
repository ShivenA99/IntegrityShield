from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List

from flask import current_app

from ...extensions import db
from ...models import PipelineRun, PipelineStage as PipelineStageModel
from ...utils.exceptions import StageExecutionFailed
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from ..developer.live_logging_service import live_logging_service
from ..developer.performance_monitor import record_metric
from ..pipeline.content_discovery_service import ContentDiscoveryService
from ..pipeline.document_enhancement_service import DocumentEnhancementService
from ..pipeline.effectiveness_testing_service import EffectivenessTestingService
from ..pipeline.pdf_creation_service import PdfCreationService
from ..pipeline.results_generation_service import ResultsGenerationService
from ..pipeline.smart_reading_service import SmartReadingService
from ..pipeline.smart_substitution_service import SmartSubstitutionService


class PipelineStageEnum(str, Enum):
    SMART_READING = "smart_reading"
    CONTENT_DISCOVERY = "content_discovery"
    SMART_SUBSTITUTION = "smart_substitution"
    EFFECTIVENESS_TESTING = "effectiveness_testing"
    DOCUMENT_ENHANCEMENT = "document_enhancement"
    PDF_CREATION = "pdf_creation"
    RESULTS_GENERATION = "results_generation"


@dataclass
class PipelineConfig:
    target_stages: Iterable[str]
    ai_models: List[str] = field(default_factory=list)
    enhancement_methods: List[str] = field(default_factory=list)
    skip_if_exists: bool = True
    parallel_processing: bool = True
    mapping_strategy: str = "unicode_steganography"
    mode: str = "detection"
    auto_vulnerability_report: bool = False
    auto_evaluation_reports: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_stages": list(self.target_stages),
            "ai_models": self.ai_models,
            "enhancement_methods": self.enhancement_methods,
            "skip_if_exists": self.skip_if_exists,
            "parallel_processing": self.parallel_processing,
            "mapping_strategy": self.mapping_strategy,
            "mode": self.mode,
            "auto_vulnerability_report": self.auto_vulnerability_report,
            "auto_evaluation_reports": self.auto_evaluation_reports,
        }


class PipelineOrchestrator:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.pipeline_order = [stage for stage in PipelineStageEnum]
        self.stage_services = {
            PipelineStageEnum.SMART_READING: SmartReadingService(),
            PipelineStageEnum.CONTENT_DISCOVERY: ContentDiscoveryService(),
            PipelineStageEnum.SMART_SUBSTITUTION: SmartSubstitutionService(),
            PipelineStageEnum.EFFECTIVENESS_TESTING: EffectivenessTestingService(),
            PipelineStageEnum.DOCUMENT_ENHANCEMENT: DocumentEnhancementService(),
            PipelineStageEnum.PDF_CREATION: PdfCreationService(),
            PipelineStageEnum.RESULTS_GENERATION: ResultsGenerationService(),
        }

    def start_background(self, run_id: str, config: PipelineConfig) -> None:
        """Start pipeline execution in background thread with error handling."""
        app = current_app._get_current_object()

        def runner():
            try:
                with app.app_context():
                    asyncio.run(self.execute_pipeline(run_id, config))
            except Exception as exc:
                # Critical: Catch all exceptions from pipeline execution
                self.logger.error(
                    f"Pipeline execution failed for run {run_id}: {exc}",
                    exc_info=True
                )

                # Update database with failure status
                try:
                    with app.app_context():
                        run = PipelineRun.query.get(run_id)
                        if run:
                            run.status = "failed"
                            run.error_details = f"Background thread exception: {str(exc)}"
                            run.completed_at = utc_now()
                            db.session.add(run)
                            db.session.commit()

                        # Emit error to live logging
                        live_logging_service.emit(
                            run_id,
                            "pipeline",
                            "ERROR",
                            f"Pipeline execution failed: {str(exc)}"
                        )
                except Exception as db_exc:
                    self.logger.error(
                        f"Failed to update run status after exception: {db_exc}",
                        exc_info=True
                    )

        thread = threading.Thread(target=runner, name=f"pipeline-{run_id}", daemon=True)
        thread.start()

    async def execute_pipeline(self, run_id: str, config: PipelineConfig) -> None:
        run = PipelineRun.query.get(run_id)
        if not run:
            self.logger.error("Pipeline run %s not found", run_id)
            return

        raw_targets = list(config.target_stages or [])
        self.logger.info(f"[{run_id}] execute_pipeline - config.target_stages: {config.target_stages}")
        self.logger.info(f"[{run_id}] execute_pipeline - raw_targets: {raw_targets}")
        self.logger.info(f"[{run_id}] execute_pipeline - config.skip_if_exists: {config.skip_if_exists}")

        if not raw_targets or "all" in raw_targets:
            target_stage_sequence = [stage for stage in self.pipeline_order]
            self.logger.info(f"[{run_id}] Using default pipeline_order: {[s.value for s in target_stage_sequence]}")
        else:
            target_stage_sequence = []
            seen: set[PipelineStageEnum] = set()
            for stage in self.pipeline_order:
                if stage.value in raw_targets and stage not in seen:
                    target_stage_sequence.append(stage)
                    seen.add(stage)
            # capture any explicit targets that are not part of the canonical order
            for stage_name in raw_targets:
                try:
                    enum_value = PipelineStageEnum(stage_name)
                except ValueError:
                    live_logging_service.emit(run_id, "pipeline", "WARNING", f"Unknown stage '{stage_name}', skipping")
                    continue
                if enum_value not in seen:
                    target_stage_sequence.append(enum_value)
                    seen.add(enum_value)

        # Prevention mode: Skip unnecessary stages
        if config.mode == "prevention":
            # Prevention mode needs:
            # - smart_reading: extract document structure
            # - content_discovery: identify question stems and locations (REQUIRED!)
            # - document_enhancement: apply attacks (ICW fixed watermark, Font random chars)
            # - pdf_creation: generate PDFs
            # - results_generation: generate reports
            # Skip: smart_substitution (no mapping generation needed), effectiveness_testing
            stages_to_skip = {
                PipelineStageEnum.SMART_SUBSTITUTION,
                PipelineStageEnum.EFFECTIVENESS_TESTING,
            }
            original_length = len(target_stage_sequence)
            target_stage_sequence = [
                stage for stage in target_stage_sequence if stage not in stages_to_skip
            ]
            skipped_count = original_length - len(target_stage_sequence)
            if skipped_count > 0:
                self.logger.info(
                    f"[{run_id}] Prevention mode: Skipped {skipped_count} stages "
                    f"(smart_substitution, effectiveness_testing)"
                )
                live_logging_service.emit(
                    run_id,
                    "pipeline",
                    "INFO",
                    f"Prevention mode: Skipping {skipped_count} unnecessary stages (smart_substitution, effectiveness_testing)",
                    context={"skipped_stages": [s.value for s in stages_to_skip]}
                )

        run.status = "running"
        db.session.add(run)
        db.session.commit()

        executed_stages: list[PipelineStageEnum] = []

        self.logger.info(f"[{run_id}] target_stage_sequence: {[s.value for s in target_stage_sequence]}")

        for stage in target_stage_sequence:
            self.logger.info(f"[{run_id}] Checking stage: {stage.value}, skip_if_exists={config.skip_if_exists}")
            if config.skip_if_exists and self._stage_already_completed(run_id, stage.value):
                self.logger.info(f"[{run_id}] Skipping {stage.value} - already completed")
                live_logging_service.emit(run_id, stage.value, "INFO", "Stage already completed, skipping")
                continue

            self.logger.info(f"[{run_id}] Executing stage: {stage.value}")
            try:
                await self._execute_stage(run_id, stage, config)
                executed_stages.append(stage)
                
                # After smart_substitution, allow pipeline to continue
                # Mapping generation is now manual-only (via UI "Generate All" button)
                # Users can generate mappings at any time, and PDF creation will use whatever mappings exist

            except Exception as exc:
                # ensure session is clean before emitting error or updating run
                try:
                    db.session.rollback()
                except Exception:
                    pass
                live_logging_service.emit(run_id, stage.value, "ERROR", str(exc))
                run.status = "failed"
                run.error_details = str(exc)
                db.session.add(run)
                db.session.commit()
                raise

        if executed_stages and executed_stages[-1] == PipelineStageEnum.RESULTS_GENERATION:
            run.status = "completed"
            run.completed_at = utc_now()
            run.current_stage = PipelineStageEnum.RESULTS_GENERATION.value
            db.session.add(run)
            db.session.commit()
            live_logging_service.emit(run_id, "pipeline", "INFO", "Pipeline completed successfully")
        else:
            run.status = "paused"
            run.completed_at = None
            if executed_stages:
                run.current_stage = executed_stages[-1].value
            db.session.add(run)
            db.session.commit()
            live_logging_service.emit(run_id, "pipeline", "INFO", "Pipeline paused", context={
                "last_stage": executed_stages[-1].value if executed_stages else None,
                "remaining_targets": [stage.value for stage in target_stage_sequence if stage not in executed_stages],
            })

    async def _execute_stage(self, run_id: str, stage: PipelineStageEnum, config: PipelineConfig) -> None:
        live_logging_service.emit(run_id, stage.value, "INFO", "Starting stage")
        stage_record = self._get_or_create_stage(run_id, stage.value)
        stage_record.status = "running"
        stage_record.started_at = utc_now()
        db.session.add(stage_record)
        db.session.commit()

        # Mark the run as currently at this stage so UI auto-navigates
        run = PipelineRun.query.get(run_id)
        if run:
            run.current_stage = stage.value
            db.session.add(run)
            db.session.commit()

        start_time = time.perf_counter()
        service = self.stage_services[stage]

        try:
            # Mark as initial run for smart_substitution stage
            stage_config = config.to_dict()
            # Mapping generation is now manual-only (via UI "Generate All" button)
            # No automatic generation during pipeline execution
            result = await service.run(run_id, stage_config)
        except Exception as exc:  # noqa: BLE001
            stage_record.status = "failed"
            stage_record.error_details = str(exc)
            stage_record.completed_at = utc_now()
            db.session.add(stage_record)
            db.session.commit()
            raise StageExecutionFailed(stage.value, str(exc)) from exc

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        stage_record.status = "completed"
        stage_record.completed_at = utc_now()
        stage_record.duration_ms = duration_ms
        stage_record.stage_data = result or {}
        db.session.add(stage_record)

        db.session.commit()

        # Auto-generate reports after stage completion (if configured)
        self._auto_generate_reports_for_stage(run_id, stage, config)

        # Sync mappings to structured.json after smart_substitution completes
        # This ensures any manually generated mappings are synced to structured.json
        if stage == PipelineStageEnum.SMART_SUBSTITUTION:
            try:
                SmartSubstitutionService().sync_structured_mappings(run_id)
                live_logging_service.emit(
                    run_id,
                    "smart_substitution",
                    "INFO",
                    "Character mapping setup completed. Use 'Generate All' button to generate mappings.",
                    component="mapping_generation",
                )
            except Exception as sync_exc:
                self.logger.warning(f"Failed to sync mappings for run {run_id}: {sync_exc}")

        record_metric(run_id, stage.value, "duration_ms", duration_ms, unit="ms")
        live_logging_service.emit(run_id, stage.value, "INFO", "Stage completed", context=result or {})

    def _get_or_create_stage(self, run_id: str, stage_name: str) -> PipelineStageModel:
        stage = PipelineStageModel.query.filter_by(pipeline_run_id=run_id, stage_name=stage_name).first()
        if stage:
            return stage
        stage = PipelineStageModel(pipeline_run_id=run_id, stage_name=stage_name, status="pending")
        db.session.add(stage)
        db.session.commit()
        return stage

    def _stage_already_completed(self, run_id: str, stage_name: str) -> bool:
        stage = PipelineStageModel.query.filter_by(pipeline_run_id=run_id, stage_name=stage_name).first()
        return stage is not None and stage.status == "completed"

    def _auto_generate_reports_for_stage(self, run_id: str, stage: PipelineStageEnum, config: PipelineConfig) -> None:
        """Auto-generate reports after specific stages complete (if configured)."""
        run = PipelineRun.query.get(run_id)
        if not run:
            return

        pipeline_config = run.pipeline_config or {}
        auto_vuln_report = pipeline_config.get("auto_vulnerability_report", False)
        auto_eval_reports = pipeline_config.get("auto_evaluation_reports", False)

        # Vulnerability report: after content_discovery (questions and gold answers available)
        if stage == PipelineStageEnum.CONTENT_DISCOVERY and auto_vuln_report:
            try:
                from ..reports.vulnerability_report_service import VulnerabilityReportService
                self.logger.info(f"[{run_id}] Auto-generating vulnerability report after content_discovery")
                vuln_service = VulnerabilityReportService()
                vuln_service.generate(run_id)
                self.logger.info(f"[{run_id}] Vulnerability report generated successfully")
            except Exception as e:
                self.logger.warning(
                    f"[{run_id}] Failed to auto-generate vulnerability report: {e}",
                    exc_info=True
                )
                # Non-blocking: Continue pipeline even if report fails

        # Detection report: after smart_substitution (mapping validation complete)
        if stage == PipelineStageEnum.SMART_SUBSTITUTION and auto_vuln_report:

            try:
                from .detection_report_service import DetectionReportService
                self.logger.info(f"[{run_id}] Auto-generating detection report after smart_substitution")
                detection_service = DetectionReportService()
                detection_service.generate(run_id)
                self.logger.info(f"[{run_id}] Detection report generated successfully")
            except Exception as e:
                self.logger.warning(
                    f"[{run_id}] Failed to auto-generate detection report: {e}",
                    exc_info=True
                )
                # Non-blocking: Continue pipeline even if report fails

        # Evaluation reports: after pdf_creation (PDFs created)
        if stage == PipelineStageEnum.PDF_CREATION and auto_eval_reports:
            enhancement_methods = pipeline_config.get("enhancement_methods", [])
            mode = pipeline_config.get("mode", "detection")
            self.logger.info(
                f"[{run_id}] Auto-generating {len(enhancement_methods)} evaluation reports "
                f"after pdf_creation (mode: {mode})"
            )

            # Use appropriate evaluation service based on mode
            if mode == "prevention":
                from ..reports.prevention_evaluation_report_service import PreventionEvaluationReportService
                eval_service = PreventionEvaluationReportService()
                report_type = "prevention evaluation"
            else:
                from ..reports.evaluation_report_service import EvaluationReportService
                eval_service = EvaluationReportService()
                report_type = "detection evaluation"

            for method in enhancement_methods:
                try:
                    self.logger.info(f"[{run_id}] Generating {report_type} report for method: {method}")
                    eval_service.generate(run_id, method=method)
                    self.logger.info(f"[{run_id}] {report_type.capitalize()} report for {method} generated successfully")
                except Exception as e:
                    self.logger.warning(
                        f"[{run_id}] Failed to generate {report_type} report for {method}: {e}",
                        exc_info=True
                    )
                    # Non-blocking: Continue with other methods even if one fails
