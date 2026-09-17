"""Add telemetry artifact metadata

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telemetry_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_key", sa.Integer(), nullable=False),
        sa.Column("driver_number", sa.Integer(), nullable=False),
        sa.Column("lap_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("storage_backend", sa.Text(), nullable=False, server_default="local"),
        sa.Column("format", sa.Text(), nullable=False, server_default="json.gz"),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
        sa.UniqueConstraint(
            "session_key",
            "driver_number",
            "lap_number",
            name="uq_telemetry_artifact_lap",
        ),
    )
    op.create_index(
        "idx_telemetry_artifacts_session_driver",
        "telemetry_artifacts",
        ["session_key", "driver_number"],
    )


def downgrade() -> None:
    op.drop_index("idx_telemetry_artifacts_session_driver", "telemetry_artifacts")
    op.drop_table("telemetry_artifacts")
