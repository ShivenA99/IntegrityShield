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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_stages": list(self.target_stages),
            "ai_models": self.ai_models,
            "enhancement_methods": self.enhancement_methods,
            "skip_if_exists": self.skip_if_exists,
            "parallel_processing": self.parallel_processing,
            "mapping_strategy": self.mapping_strategy,
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
        app = current_app._get_current_object()

        def runner():
            with app.app_context():
                asyncio.run(self.execute_pipeline(run_id, config))

        thread = threading.Thread(target=runner, name=f"pipeline-{run_id}", daemon=True)
        thread.start()

    async def execute_pipeline(self, run_id: str, config: PipelineConfig) -> None:
        run = PipelineRun.query.get(run_id)
        if not run:
            self.logger.error("Pipeline run %s not found", run_id)
            return

        raw_targets = list(config.target_stages or [])
        if not raw_targets or "all" in raw_targets:
            target_stage_sequence = [stage for stage in self.pipeline_order]
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

        run.status = "running"
        db.session.add(run)
        db.session.commit()

        executed_stages: list[PipelineStageEnum] = []

        for stage in target_stage_sequence:
            if config.skip_if_exists and self._stage_already_completed(run_id, stage.value):
                live_logging_service.emit(run_id, stage.value, "INFO", "Stage already completed, skipping")
                continue

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
