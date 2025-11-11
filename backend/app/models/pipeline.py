from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


json_type = JSON().with_variant(JSONB(), "postgresql")


class TimestampMixin:
    created_at: Mapped[Any] = mapped_column(db.DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Any] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PipelineRun(db.Model, TimestampMixin):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_pdf_path: Mapped[str] = mapped_column(db.Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(db.Text, nullable=False)
    current_stage: Mapped[str] = mapped_column(db.String(64), nullable=False, default="smart_reading")
    status: Mapped[str] = mapped_column(db.String(32), nullable=False, default="pending")
    structured_data: Mapped[dict] = mapped_column(json_type, default=dict)
    pipeline_config: Mapped[dict] = mapped_column(json_type, default=dict)
    processing_stats: Mapped[dict] = mapped_column(json_type, default=dict)
    error_details: Mapped[Optional[str]] = mapped_column(db.Text)
    completed_at: Mapped[Optional[Any]] = mapped_column(db.DateTime(timezone=True))

    stages: Mapped[list["PipelineStage"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    questions: Mapped[list["QuestionManipulation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    enhanced_pdfs: Mapped[list["EnhancedPDF"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    logs: Mapped[list["PipelineLog"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    metrics: Mapped[list["PerformanceMetric"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    character_mappings: Mapped[list["CharacterMapping"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    ai_model_results: Mapped[list["AIModelResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )


class PipelineStage(db.Model, TimestampMixin):
    __tablename__ = "pipeline_stages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(db.String(36), db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    stage_name: Mapped[str] = mapped_column(db.String(64), nullable=False)
    status: Mapped[str] = mapped_column(db.String(32), nullable=False, default="pending")
    stage_data: Mapped[dict] = mapped_column(json_type, default=dict)
    duration_ms: Mapped[Optional[int]] = mapped_column(db.Integer)
    memory_usage_mb: Mapped[Optional[float]] = mapped_column(db.Float)
    error_details: Mapped[Optional[str]] = mapped_column(db.Text)
    started_at: Mapped[Optional[Any]] = mapped_column(db.DateTime(timezone=True))
    completed_at: Mapped[Optional[Any]] = mapped_column(db.DateTime(timezone=True))

    run: Mapped[PipelineRun] = relationship(back_populates="stages")


class QuestionManipulation(db.Model, TimestampMixin):
    __tablename__ = "question_manipulations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(db.String(36), db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    question_number: Mapped[str] = mapped_column(db.String(32), nullable=False)
    question_type: Mapped[str] = mapped_column(db.String(32), nullable=False)
    original_text: Mapped[str] = mapped_column(db.Text, nullable=False)
    stem_position: Mapped[Optional[dict]] = mapped_column(json_type, default=dict)
    options_data: Mapped[Optional[dict]] = mapped_column(json_type, default=dict)
    gold_answer: Mapped[Optional[str]] = mapped_column(db.String(32))
    gold_confidence: Mapped[Optional[float]] = mapped_column(db.Float)
    manipulation_method: Mapped[Optional[str]] = mapped_column(db.String(64))
    substring_mappings: Mapped[Optional[list]] = mapped_column(json_type, nullable=True)
    effectiveness_score: Mapped[Optional[float]] = mapped_column(db.Float)
    ai_model_results: Mapped[dict] = mapped_column(json_type, default=dict)
    visual_elements: Mapped[Optional[list]] = mapped_column(json_type, nullable=True)
    sequence_index: Mapped[int] = mapped_column(db.Integer, nullable=False, server_default="0")
    source_identifier: Mapped[Optional[str]] = mapped_column(db.String(255))

    run: Mapped[PipelineRun] = relationship(back_populates="questions")
    ai_results: Mapped[list["AIModelResult"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", lazy="selectin"
    )


class CharacterMapping(db.Model, TimestampMixin):
    __tablename__ = "character_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(db.String(36), db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    mapping_strategy: Mapped[str] = mapped_column(db.String(64), nullable=False)
    character_map: Mapped[dict] = mapped_column(json_type, nullable=False)
    usage_statistics: Mapped[dict] = mapped_column(json_type, default=dict)
    effectiveness_metrics: Mapped[dict] = mapped_column(json_type, default=dict)
    generation_config: Mapped[dict] = mapped_column(json_type, default=dict)

    run: Mapped[PipelineRun] = relationship(back_populates="character_mappings")


class EnhancedPDF(db.Model, TimestampMixin):
    __tablename__ = "enhanced_pdfs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(db.String(36), db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    method_name: Mapped[str] = mapped_column(db.String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(db.Text, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(db.Integer)
    generation_config: Mapped[dict] = mapped_column(json_type, default=dict)
    effectiveness_stats: Mapped[dict] = mapped_column(json_type, default=dict)
    validation_results: Mapped[dict] = mapped_column(json_type, default=dict)
    visual_quality_score: Mapped[Optional[float]] = mapped_column(db.Float)

    run: Mapped[PipelineRun] = relationship(back_populates="enhanced_pdfs")


class PipelineLog(db.Model):
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(db.String(36), db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(db.String(64), nullable=False)
    level: Mapped[str] = mapped_column(db.String(16), nullable=False)
    message: Mapped[str] = mapped_column(db.Text, nullable=False)
    context: Mapped[dict] = mapped_column(json_type, default=dict)
    component: Mapped[Optional[str]] = mapped_column(db.String(128))
    timestamp: Mapped[Any] = mapped_column(db.DateTime(timezone=True), server_default=func.now())

    run: Mapped[PipelineRun] = relationship(back_populates="logs")


class PerformanceMetric(db.Model, TimestampMixin):
    __tablename__ = "performance_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(db.String(36), db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(db.String(64), nullable=False)
    metric_name: Mapped[str] = mapped_column(db.String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(db.Float, nullable=False)
    metric_unit: Mapped[Optional[str]] = mapped_column(db.String(32))
    details: Mapped[dict] = mapped_column(json_type, default=dict)

    run: Mapped[PipelineRun] = relationship(back_populates="metrics")


class AIModelResult(db.Model, TimestampMixin):
    __tablename__ = "ai_model_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(db.String(36), db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey("question_manipulations.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(db.String(64), nullable=False)
    original_answer: Mapped[Optional[str]] = mapped_column(db.Text)
    original_confidence: Mapped[Optional[float]] = mapped_column(db.Float)
    manipulated_answer: Mapped[Optional[str]] = mapped_column(db.Text)
    manipulated_confidence: Mapped[Optional[float]] = mapped_column(db.Float)
    was_fooled: Mapped[Optional[bool]] = mapped_column(db.Boolean)
    response_time_ms: Mapped[Optional[int]] = mapped_column(db.Integer)
    api_cost_cents: Mapped[Optional[float]] = mapped_column(db.Float)
    full_response: Mapped[dict] = mapped_column(json_type, default=dict)
    tested_at: Mapped[Any] = mapped_column(db.DateTime(timezone=True), server_default=func.now())

    run: Mapped[PipelineRun] = relationship(back_populates="ai_model_results")
    question: Mapped[QuestionManipulation] = relationship(back_populates="ai_results")


class SystemConfig(db.Model, TimestampMixin):
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(db.String(128), unique=True, nullable=False)
    config_value: Mapped[dict] = mapped_column(json_type, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(db.Text)
    is_secret: Mapped[bool] = mapped_column(db.Boolean, default=False)
