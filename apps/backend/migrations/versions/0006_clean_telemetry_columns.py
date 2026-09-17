"""Remove duplicate telemetry columns (distance/x/y aliases)

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision      = '0006'
down_revision = '0005'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Drop the old duplicate columns added by migration 0003
    # Data lives in distance_m, x_pos, y_pos — those are correct
    op.drop_column('telemetry', 'distance')
    op.drop_column('telemetry', 'x')
    op.drop_column('telemetry', 'y')

    # Add a proper serial id for deterministic ordering
    # (TimescaleDB chunks don't guarantee insertion order)
    op.execute("""
        ALTER TABLE telemetry
        ADD COLUMN IF NOT EXISTS sample_order SERIAL
    """)


def downgrade() -> None:
    op.add_column('telemetry', sa.Column('distance', sa.Float(), nullable=True))
    op.add_column('telemetry', sa.Column('x',        sa.Float(), nullable=True))
    op.add_column('telemetry', sa.Column('y',        sa.Float(), nullable=True))
    op.drop_column('telemetry', 'sample_order')
