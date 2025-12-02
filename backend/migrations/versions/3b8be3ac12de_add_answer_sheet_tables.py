"""add answer sheet tables

Revision ID: 3b8be3ac12de
Revises: 1bbf3edc9f23
Create Date: 2025-11-12 08:45:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3b8be3ac12de"
down_revision = "1bbf3edc9f23"
branch_labels = None
depends_on = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "answer_sheet_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("config", json_type, nullable=False),
        sa.Column("summary", json_type, nullable=False),
        sa.Column("total_students", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pipeline_run_id"),
    )
    op.create_index(
        op.f("ix_answer_sheet_runs_pipeline_run_id"),
        "answer_sheet_runs",
        ["pipeline_run_id"],
        unique=False,
    )

    op.create_table(
        "answer_sheet_students",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("student_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("is_cheating", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cheating_strategy", sa.String(length=32), nullable=True),
        sa.Column("copy_fraction", sa.Float(), nullable=True),
        sa.Column("paraphrase_style", sa.String(length=32), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("metadata", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["answer_sheet_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "student_key", name="uq_answer_sheet_students_run_student"),
    )
    op.create_index(
        op.f("ix_answer_sheet_students_pipeline_run_id"),
        "answer_sheet_students",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_answer_sheet_students_run_id"),
        "answer_sheet_students",
        ["run_id"],
        unique=False,
    )

    op.create_table(
        "answer_sheet_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=True),
        sa.Column("question_number", sa.String(length=32), nullable=False),
        sa.Column("question_type", sa.String(length=32), nullable=True),
        sa.Column("cheating_source", sa.String(length=32), nullable=False, server_default=sa.text("'fair'")),
        sa.Column("source_reference", sa.String(length=128), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("paraphrased", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("metadata", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["question_manipulations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["answer_sheet_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["answer_sheet_students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_answer_sheet_records_pipeline_run_id"),
        "answer_sheet_records",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_answer_sheet_records_run_id"),
        "answer_sheet_records",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_answer_sheet_records_student_id"),
        "answer_sheet_records",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_answer_sheet_records_question_id"),
        "answer_sheet_records",
        ["question_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_answer_sheet_records_question_id"), table_name="answer_sheet_records")
    op.drop_index(op.f("ix_answer_sheet_records_student_id"), table_name="answer_sheet_records")
    op.drop_index(op.f("ix_answer_sheet_records_run_id"), table_name="answer_sheet_records")
    op.drop_index(op.f("ix_answer_sheet_records_pipeline_run_id"), table_name="answer_sheet_records")
    op.drop_table("answer_sheet_records")

    op.drop_index(op.f("ix_answer_sheet_students_run_id"), table_name="answer_sheet_students")
    op.drop_index(op.f("ix_answer_sheet_students_pipeline_run_id"), table_name="answer_sheet_students")
    op.drop_table("answer_sheet_students")

    op.drop_index(op.f("ix_answer_sheet_runs_pipeline_run_id"), table_name="answer_sheet_runs")
    op.drop_table("answer_sheet_runs")

