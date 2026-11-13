"""Add race control events storage

Revision ID: 0021
Revises: 0020
"""

from alembic import op
import sqlalchemy as sa


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "race_control_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("flag", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("driver_number", sa.Integer(), nullable=True),
        sa.Column("sector", sa.Integer(), nullable=True),
        sa.Column("lap_number", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
    )
    op.create_index(
        "idx_race_control_session_lap",
        "race_control_events",
        ["session_key", "lap_number"],
    )
    op.create_index(
        "idx_race_control_session_driver",
        "race_control_events",
        ["session_key", "driver_number"],
    )


def downgrade() -> None:
    op.drop_index("idx_race_control_session_driver", "race_control_events")
    op.drop_index("idx_race_control_session_lap", "race_control_events")
    op.drop_table("race_control_events")
