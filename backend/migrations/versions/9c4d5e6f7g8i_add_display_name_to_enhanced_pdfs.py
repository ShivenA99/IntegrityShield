"""add display_name to enhanced_pdfs

Revision ID: 9c4d5e6f7g8i
Revises: 8a3d4e5f6g7h
Create Date: 2025-12-01 10:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9c4d5e6f7g8i"
down_revision = "8a3d4e5f6g7h"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column already exists before adding
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("enhanced_pdfs")]

    if "display_name" not in columns:
        # Add display_name column only if it doesn't exist
        op.add_column(
            "enhanced_pdfs",
            sa.Column("display_name", sa.String(length=128), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("enhanced_pdfs", "display_name")
