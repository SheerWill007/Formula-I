"""Add quali_segment to lap_times

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('lap_times', sa.Column('quali_segment', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('lap_times', 'quali_segment')
