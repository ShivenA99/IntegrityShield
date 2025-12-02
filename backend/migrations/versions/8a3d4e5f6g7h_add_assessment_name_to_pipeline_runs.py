"""add assessment_name to pipeline_runs

Revision ID: 8a3d4e5f6g7h
Revises: 7f2b8c19fb8c
Create Date: 2025-11-29 19:30:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8a3d4e5f6g7h"
down_revision = "7f2b8c19fb8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column already exists before adding
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("pipeline_runs")]

    if "assessment_name" not in columns:
        # Add assessment_name column only if it doesn't exist
        op.add_column(
            "pipeline_runs",
            sa.Column("assessment_name", sa.String(length=255), nullable=True),
        )

        # Optionally backfill from original_filename
        bind.execute(
            sa.text(
                "UPDATE pipeline_runs "
                "SET assessment_name = original_filename "
                "WHERE assessment_name IS NULL AND original_filename IS NOT NULL"
            )
        )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "assessment_name")
