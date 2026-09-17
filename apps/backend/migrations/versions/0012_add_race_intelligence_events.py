"""Add race intelligence event storage

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "race_intelligence_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("driver_number", sa.Integer(), nullable=True),
        sa.Column("lap_number", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
        sa.UniqueConstraint(
            "session_key",
            "event_type",
            "event_key",
            name="uq_race_intelligence_event",
        ),
    )
    op.create_index(
        "idx_race_intelligence_events_session_type",
        "race_intelligence_events",
        ["session_key", "event_type"],
    )
    op.create_index(
        "idx_race_intelligence_events_driver",
        "race_intelligence_events",
        ["session_key", "driver_number"],
    )


def downgrade() -> None:
    op.drop_index("idx_race_intelligence_events_driver", "race_intelligence_events")
    op.drop_index("idx_race_intelligence_events_session_type", "race_intelligence_events")
    op.drop_table("race_intelligence_events")
