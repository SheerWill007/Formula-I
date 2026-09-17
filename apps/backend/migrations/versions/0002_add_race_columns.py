"""add race columns to lap_times

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-01
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('lap_times', sa.Column('stint',           sa.Integer(),     nullable=True))
    op.add_column('lap_times', sa.Column('position',        sa.Integer(),     nullable=True))
    op.add_column('lap_times', sa.Column('fresh_tyre',      sa.Boolean(),     nullable=True))
    op.add_column('lap_times', sa.Column('deleted_reason',  sa.Text(),        nullable=True))
    op.add_column('lap_times', sa.Column('is_accurate',     sa.Boolean(),     nullable=True))
    op.add_column('lap_times', sa.Column('speed_i1',        sa.Float(),       nullable=True))
    op.add_column('lap_times', sa.Column('speed_i2',        sa.Float(),       nullable=True))
    op.add_column('lap_times', sa.Column('speed_fl',        sa.Float(),       nullable=True))
    op.add_column('lap_times', sa.Column('speed_st',        sa.Float(),       nullable=True))


def downgrade() -> None:
    for col in ['stint','position','fresh_tyre','deleted_reason','is_accurate',
                'speed_i1','speed_i2','speed_fl','speed_st']:
        op.drop_column('lap_times', col)
