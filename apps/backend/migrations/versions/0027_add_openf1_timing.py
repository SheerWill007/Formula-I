"""Add OpenF1 intervals, position changes and pit stops

Revision ID: 0027
Revises: 0026
"""

from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Gap to leader / car ahead, sampled by OpenF1 roughly every 4 seconds.
    op.create_table(
        "session_intervals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("driver_number", sa.Integer(), nullable=False),
        sa.Column("date", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=True),
        sa.Column("gap_to_leader_s", sa.Float(), nullable=True),
        sa.Column("interval_s", sa.Float(), nullable=True),
        # Lapped cars come back as "+1 LAP" strings; keep the raw text.
        sa.Column("gap_to_leader_raw", sa.Text(), nullable=True),
        sa.Column("interval_raw", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
    )
    op.create_index(
        "idx_session_intervals_session_driver",
        "session_intervals",
        ["session_key", "driver_number", "date"],
    )

    # One row per race-order change.
    op.create_table(
        "position_changes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("driver_number", sa.Integer(), nullable=False),
        sa.Column("date", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
    )
    op.create_index(
        "idx_position_changes_session_driver",
        "position_changes",
        ["session_key", "driver_number", "date"],
    )

    op.create_table(
        "pit_stops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("driver_number", sa.Integer(), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=False),
        sa.Column("date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("pit_duration_s", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
        sa.UniqueConstraint(
            "session_key", "driver_number", "lap_number", name="uq_pit_stops_lap"
        ),
    )


def downgrade() -> None:
    op.drop_table("pit_stops")
    op.drop_index("idx_position_changes_session_driver", "position_changes")
    op.drop_table("position_changes")
    op.drop_index("idx_session_intervals_session_driver", "session_intervals")
    op.drop_table("session_intervals")
