"""
Add driver features for ML embedding pipeline

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "driver_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver_number", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("abbreviation", sa.Text(), nullable=False),
        sa.Column("team_name", sa.Text(), nullable=True),
        # Race performance
        sa.Column("avg_finish_position", sa.Float(), nullable=True),
        sa.Column("finish_position_stddev", sa.Float(), nullable=True),
        sa.Column("podium_rate", sa.Float(), nullable=True),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("avg_positions_gained", sa.Float(), nullable=True),
        sa.Column("quali_to_race_delta", sa.Float(), nullable=True),
        sa.Column("dnf_rate", sa.Float(), nullable=True),
        # Pace metrics
        sa.Column("lap_time_consistency", sa.Float(), nullable=True),
        sa.Column("avg_speed_trap", sa.Float(), nullable=True),
        # Driving style (from telemetry)
        sa.Column("max_speed_capability", sa.Float(), nullable=True),
        sa.Column("braking_aggression", sa.Float(), nullable=True),
        sa.Column("drs_usage_pct", sa.Float(), nullable=True),
        # Wet weather
        sa.Column("wet_pace_delta", sa.Float(), nullable=True),
        # Meta data
        sa.Column(
            "computed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "driver_number", "season", name="uq_driver_features_driver_season"
        ),
    )

    op.create_index(
        "idx_driver_features_season",
        "driver_features",
        ["season"],
    )


def downgrade() -> None:
    op.drop_index("idx_driver_features_season", "driver_features")
    op.drop_table("driver_features")
