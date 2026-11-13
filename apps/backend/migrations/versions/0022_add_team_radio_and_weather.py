"""Add team radio and weather event storage

Revision ID: 0022
Revises: 0021
"""

from alembic import op
import sqlalchemy as sa


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_radio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("driver_number", sa.Integer(), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=True),
        sa.Column("date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("recording_url", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
    )
    op.create_index(
        "idx_team_radio_session_driver",
        "team_radio",
        ["session_key", "driver_number"],
    )
    op.create_index(
        "idx_team_radio_session_lap",
        "team_radio",
        ["session_key", "lap_number"],
    )

    op.create_table(
        "weather_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=True),
        sa.Column("track_temp_c", sa.Float(), nullable=True),
        sa.Column("air_temp_c", sa.Float(), nullable=True),
        sa.Column("humidity_pct", sa.Float(), nullable=True),
        sa.Column("rainfall", sa.Boolean(), nullable=True),
        sa.Column("wind_speed_ms", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
    )
    op.create_index(
        "idx_weather_events_session_lap",
        "weather_events",
        ["session_key", "lap_number"],
    )


def downgrade() -> None:
    op.drop_index("idx_weather_events_session_lap", "weather_events")
    op.drop_table("weather_events")
    op.drop_index("idx_team_radio_session_lap", "team_radio")
    op.drop_index("idx_team_radio_session_driver", "team_radio")
    op.drop_table("team_radio")
