"""support multiple classroom datasets and evaluations

Revision ID: 7f2b8c19fb8c
Revises: 3b8be3ac12de
Create Date: 2025-11-14 10:05:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "7f2b8c19fb8c"
down_revision = "3b8be3ac12de"
branch_labels = None
depends_on = None


json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    # answer_sheet_runs enhacements
    op.drop_constraint("answer_sheet_runs_pipeline_run_id_key", "answer_sheet_runs", type_="unique")
    op.add_column("answer_sheet_runs", sa.Column("classroom_key", sa.String(length=64), nullable=True))
    op.add_column("answer_sheet_runs", sa.Column("classroom_label", sa.String(length=128), nullable=True))
    op.add_column("answer_sheet_runs", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("answer_sheet_runs", sa.Column("attacked_pdf_method", sa.String(length=64), nullable=True))
    op.add_column("answer_sheet_runs", sa.Column("attacked_pdf_path", sa.Text(), nullable=True))
    op.add_column("answer_sheet_runs", sa.Column("origin", sa.String(length=32), nullable=False, server_default=sa.text("'generated'")))
    op.add_column("answer_sheet_runs", sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'ready'")))
    op.add_column("answer_sheet_runs", sa.Column("artifacts", json_type, nullable=False, server_default=sa.text("'{}'")))
    op.add_column("answer_sheet_runs", sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        "uq_answer_sheet_runs_pipeline_classroom",
        "answer_sheet_runs",
        ["pipeline_run_id", "classroom_key"],
    )
    op.create_index(
        op.f("ix_answer_sheet_runs_classroom_key"),
        "answer_sheet_runs",
        ["classroom_key"],
        unique=False,
    )

    # classroom evaluations table
    op.create_table(
        "classroom_evaluations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("answer_sheet_run_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("summary", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("artifacts", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evaluation_config", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["answer_sheet_run_id"],
            ["answer_sheet_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_sheet_run_id"),
    )
    op.create_index(
        op.f("ix_classroom_evaluations_pipeline_run_id"),
        "classroom_evaluations",
        ["pipeline_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_classroom_evaluations_pipeline_run_id"), table_name="classroom_evaluations")
    op.drop_table("classroom_evaluations")

    op.drop_index(op.f("ix_answer_sheet_runs_classroom_key"), table_name="answer_sheet_runs")
    op.drop_constraint("uq_answer_sheet_runs_pipeline_classroom", "answer_sheet_runs", type_="unique")
    op.drop_column("answer_sheet_runs", "last_evaluated_at")
    op.drop_column("answer_sheet_runs", "artifacts")
    op.drop_column("answer_sheet_runs", "status")
    op.drop_column("answer_sheet_runs", "origin")
    op.drop_column("answer_sheet_runs", "attacked_pdf_path")
    op.drop_column("answer_sheet_runs", "attacked_pdf_method")
    op.drop_column("answer_sheet_runs", "notes")
    op.drop_column("answer_sheet_runs", "classroom_label")
    op.drop_column("answer_sheet_runs", "classroom_key")
    op.create_unique_constraint("answer_sheet_runs_pipeline_run_id_key", "answer_sheet_runs", ["pipeline_run_id"])
