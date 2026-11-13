"""Index telemetry by lap so one-lap reads stop scanning a driver's whole session

Revision ID: 0030
Revises: 0029
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_telemetry_session_driver_lap
        ON telemetry (session_key, driver_number, lap_number, distance_m)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_telemetry_session_driver_lap")
