"""Add kerb-usage features to driver_features

Revision ID: 0015
Revises: 0014
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "driver_features",
        sa.Column("throttle_instability", sa.Float(), nullable=True),
    )
    op.add_column(
        "driver_features",
        sa.Column("kerb_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "driver_features",
        sa.Column("track_limits_rate", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("driver_features", "track_limits_rate")
    op.drop_column("driver_features", "kerb_confidence")
    op.drop_column("driver_features", "throttle_instability")
