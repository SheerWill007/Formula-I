"""add distance and xy to telemetry

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision      = '0003'
down_revision = '0002'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column('telemetry', sa.Column('distance', sa.Float(), nullable=True))
    op.add_column('telemetry', sa.Column('x',        sa.Float(), nullable=True))
    op.add_column('telemetry', sa.Column('y',        sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('telemetry', 'distance')
    op.drop_column('telemetry', 'x')
    op.drop_column('telemetry', 'y')
