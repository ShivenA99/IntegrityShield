"""add sequence index and source identifier to questions

Revision ID: 1bbf3edc9f23
Revises: 67a5277896d5
Create Date: 2025-11-07 21:13:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1bbf3edc9f23"
down_revision = "67a5277896d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("question_manipulations", sa.Column("sequence_index", sa.Integer(), nullable=True))
    op.add_column("question_manipulations", sa.Column("source_identifier", sa.String(length=255), nullable=True))

    bind = op.get_bind()
    question_rows = list(
        bind.execute(
            sa.text(
                "SELECT id, pipeline_run_id FROM question_manipulations ORDER BY pipeline_run_id, id"
            )
        )
    )

    current_run = None
    current_index = 0
    update_params = []
    for row in question_rows:
        run_id = row.pipeline_run_id
        if run_id != current_run:
            current_run = run_id
            current_index = 0
        update_params.append(
            {
                "id": row.id,
                "sequence_index": current_index,
                "source_identifier": f"legacy-{row.id}",
            }
        )
        current_index += 1

    if update_params:
        bind.execute(
            sa.text(
                "UPDATE question_manipulations "
                "SET sequence_index = :sequence_index, source_identifier = :source_identifier "
                "WHERE id = :id"
            ),
            update_params,
        )

    op.alter_column(
        "question_manipulations",
        "sequence_index",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="0",
    )


def downgrade() -> None:
    op.drop_column("question_manipulations", "source_identifier")
    op.drop_column("question_manipulations", "sequence_index")





