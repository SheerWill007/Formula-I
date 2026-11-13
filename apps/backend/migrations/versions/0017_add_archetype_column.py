"""Add archetype column to driver_embeddings

Revision ID: 0017
Revises: 0016
"""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "driver_embeddings",
        sa.Column("archetype", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("driver_embeddings", "archetype")
