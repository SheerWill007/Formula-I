"""Add session results and track status periods

Revision ID: 0026
Revises: 0025
"""

from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_results",
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("driver_number", sa.Integer(), nullable=False),
        sa.Column("abbreviation", sa.Text(), nullable=True),
        sa.Column("team_name", sa.Text(), nullable=True),
        sa.Column("grid_position", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("classified_position", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("points", sa.Float(), nullable=True),
        sa.Column("laps_completed", sa.Integer(), nullable=True),
        sa.Column("race_time_ms", sa.Float(), nullable=True),
        sa.Column("q1_ms", sa.Float(), nullable=True),
        sa.Column("q2_ms", sa.Float(), nullable=True),
        sa.Column("q3_ms", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("session_key", "driver_number"),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
    )
    op.create_index("idx_session_results_session", "session_results", ["session_key"])

    op.create_table(
        "track_status_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        # FastF1 codes: 1 AllClear, 2 Yellow, 4 SafetyCar, 5 Red,
        # 6 VirtualSafetyCar, 7 VSCEnding
        sa.Column("status_code", sa.Text(), nullable=False),
        sa.Column("status_label", sa.Text(), nullable=False),
        # Session-relative clock (ms since session t0); end is NULL for the
        # final period, which runs until the session ends.
        sa.Column("start_ms", sa.Float(), nullable=False),
        sa.Column("end_ms", sa.Float(), nullable=True),
        sa.Column("start_lap", sa.Integer(), nullable=True),
        sa.Column("end_lap", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
    )
    op.create_index(
        "idx_track_status_session", "track_status_periods", ["session_key", "start_ms"]
    )


def downgrade() -> None:
    op.drop_index("idx_track_status_session", "track_status_periods")
    op.drop_table("track_status_periods")
    op.drop_index("idx_session_results_session", "session_results")
    op.drop_table("session_results")
