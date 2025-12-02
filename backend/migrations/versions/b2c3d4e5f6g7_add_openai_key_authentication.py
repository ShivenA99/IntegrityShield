"""add openai key authentication fields

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2025-12-02 12:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make email and password_hash nullable (transition to OpenAI key auth)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(length=255), nullable=True)
        batch_op.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)

        # Add OpenAI key fields
        batch_op.add_column(sa.Column("openai_key_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("encrypted_openai_key", sa.Text(), nullable=True))

    # Drop unique constraint on email
    op.drop_index("ix_users_email", table_name="users")

    # Create non-unique index on email
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    # Create unique index on openai_key_hash
    op.create_index("ix_users_openai_key_hash", "users", ["openai_key_hash"], unique=True)


def downgrade() -> None:
    # Remove OpenAI key index
    op.drop_index("ix_users_openai_key_hash", table_name="users")

    # Restore unique email index
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Remove OpenAI key fields and restore constraints
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("encrypted_openai_key")
        batch_op.drop_column("openai_key_hash")
        batch_op.alter_column("password_hash", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("email", existing_type=sa.String(length=255), nullable=False)
