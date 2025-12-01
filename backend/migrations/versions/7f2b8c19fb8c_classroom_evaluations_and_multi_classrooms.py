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
    # Use batch mode for SQLite compatibility (copy-and-move strategy)
    with op.batch_alter_table("answer_sheet_runs", schema=None) as batch_op:
        batch_op.drop_constraint("answer_sheet_runs_pipeline_run_id_key", type_="unique")
        batch_op.add_column(sa.Column("classroom_key", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("classroom_label", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("attacked_pdf_method", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("attacked_pdf_path", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("origin", sa.String(length=32), nullable=False, server_default=sa.text("'generated'")))
        batch_op.add_column(sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'ready'")))
        batch_op.add_column(sa.Column("artifacts", json_type, nullable=False, server_default=sa.text("'{}'")))
        batch_op.add_column(sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint(
            "uq_answer_sheet_runs_pipeline_classroom",
            ["pipeline_run_id", "classroom_key"],
        )
        batch_op.create_index(
            op.f("ix_answer_sheet_runs_classroom_key"),
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

    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("answer_sheet_runs", schema=None) as batch_op:
        batch_op.drop_index(op.f("ix_answer_sheet_runs_classroom_key"))
        batch_op.drop_constraint("uq_answer_sheet_runs_pipeline_classroom", type_="unique")
        batch_op.drop_column("last_evaluated_at")
        batch_op.drop_column("artifacts")
        batch_op.drop_column("status")
        batch_op.drop_column("origin")
        batch_op.drop_column("attacked_pdf_path")
        batch_op.drop_column("attacked_pdf_method")
        batch_op.drop_column("notes")
        batch_op.drop_column("classroom_label")
        batch_op.drop_column("classroom_key")
        batch_op.create_unique_constraint("answer_sheet_runs_pipeline_run_id_key", ["pipeline_run_id"])
