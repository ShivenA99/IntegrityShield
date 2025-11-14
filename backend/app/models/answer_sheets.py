from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .pipeline import (
    PipelineRun,
    QuestionManipulation,
    TimestampMixin,
    json_type,
)


class AnswerSheetRun(db.Model, TimestampMixin):
    __tablename__ = "answer_sheet_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(
        db.String(36),
        db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    classroom_key: Mapped[Optional[str]] = mapped_column(db.String(64), nullable=True)
    classroom_label: Mapped[Optional[str]] = mapped_column(db.String(128), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    attacked_pdf_method: Mapped[Optional[str]] = mapped_column(db.String(64), nullable=True)
    attacked_pdf_path: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    origin: Mapped[str] = mapped_column(db.String(32), nullable=False, default="generated")
    status: Mapped[str] = mapped_column(db.String(32), nullable=False, default="ready")
    config: Mapped[dict] = mapped_column(json_type, default=dict)
    summary: Mapped[dict] = mapped_column(json_type, default=dict)
    total_students: Mapped[int] = mapped_column(db.Integer, default=0)
    artifacts: Mapped[dict] = mapped_column(json_type, default=dict)
    last_evaluated_at: Mapped[Optional[Any]] = mapped_column(db.DateTime(timezone=True), nullable=True)

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="answer_sheet_runs")
    students: Mapped[list["AnswerSheetStudent"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    records: Mapped[list["AnswerSheetRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    evaluation: Mapped[Optional["ClassroomEvaluation"]] = relationship(
        "ClassroomEvaluation",
        back_populates="classroom_run",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )


class AnswerSheetStudent(db.Model, TimestampMixin):
    __tablename__ = "answer_sheet_students"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("answer_sheet_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        db.String(36),
        db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_key: Mapped[str] = mapped_column(db.String(64), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(db.String(128))
    is_cheating: Mapped[bool] = mapped_column(db.Boolean, default=False)
    cheating_strategy: Mapped[Optional[str]] = mapped_column(db.String(32))
    copy_fraction: Mapped[Optional[float]] = mapped_column(db.Float)
    paraphrase_style: Mapped[Optional[str]] = mapped_column(db.String(32))
    score: Mapped[Optional[float]] = mapped_column(db.Float)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_type, default=dict)

    run: Mapped[AnswerSheetRun] = relationship(back_populates="students")
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="answer_sheet_students")
    records: Mapped[list["AnswerSheetRecord"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ClassroomEvaluation(db.Model, TimestampMixin):
    __tablename__ = "classroom_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    answer_sheet_run_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("answer_sheet_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        db.String(36),
        db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(db.String(32), nullable=False, default="pending")
    summary: Mapped[dict] = mapped_column(json_type, default=dict)
    artifacts: Mapped[dict] = mapped_column(json_type, default=dict)
    evaluation_config: Mapped[dict] = mapped_column(json_type, default=dict)
    completed_at: Mapped[Optional[Any]] = mapped_column(db.DateTime(timezone=True), nullable=True)

    classroom_run: Mapped[AnswerSheetRun] = relationship(back_populates="evaluation")
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="classroom_evaluations")


class AnswerSheetRecord(db.Model, TimestampMixin):
    __tablename__ = "answer_sheet_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("answer_sheet_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("answer_sheet_students.id", ondelete="CASCADE"),
        nullable=False,
    )
    pipeline_run_id: Mapped[str] = mapped_column(
        db.String(36),
        db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[Optional[int]] = mapped_column(
        db.Integer,
        db.ForeignKey("question_manipulations.id", ondelete="SET NULL"),
    )
    question_number: Mapped[str] = mapped_column(db.String(32))
    question_type: Mapped[Optional[str]] = mapped_column(db.String(32))
    cheating_source: Mapped[str] = mapped_column(db.String(32), default="fair")
    source_reference: Mapped[Optional[str]] = mapped_column(db.String(128))
    answer_text: Mapped[str] = mapped_column(db.Text)
    paraphrased: Mapped[bool] = mapped_column(db.Boolean, default=False)
    score: Mapped[Optional[float]] = mapped_column(db.Float)
    confidence: Mapped[Optional[float]] = mapped_column(db.Float)
    is_correct: Mapped[Optional[bool]] = mapped_column(db.Boolean)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_type, default=dict)

    run: Mapped[AnswerSheetRun] = relationship(back_populates="records")
    student: Mapped[AnswerSheetStudent] = relationship(back_populates="records")
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="answer_sheet_records")
    question: Mapped[Optional[QuestionManipulation]] = relationship(lazy="selectin")
