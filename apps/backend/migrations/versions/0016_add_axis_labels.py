"""Add axis_labels column to driver_embeddings

Revision ID: 0016
Revises: 0015
"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "driver_embeddings",
        sa.Column("axis_labels", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("driver_embeddings", "axis_labels")
