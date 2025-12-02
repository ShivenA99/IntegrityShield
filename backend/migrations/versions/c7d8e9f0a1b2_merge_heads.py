"""merge heads

Revision ID: c7d8e9f0a1b2
Revises: 9c4d5e6f7g8i, b2c3d4e5f6g7
Create Date: 2025-12-02 13:50:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7d8e9f0a1b2"
down_revision = ("9c4d5e6f7g8i", "b2c3d4e5f6g7")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a merge migration - no schema changes needed
    pass


def downgrade() -> None:
    # This is a merge migration - no schema changes needed
    pass
