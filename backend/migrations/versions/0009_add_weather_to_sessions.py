"""Add weather columns to sessions table

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision      = '0009'
down_revision = '0008'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('track_temp_c',  sa.Float(), nullable=True))
    op.add_column('sessions', sa.Column('air_temp_c',    sa.Float(), nullable=True))
    op.add_column('sessions', sa.Column('humidity_pct',  sa.Float(), nullable=True))
    op.add_column('sessions', sa.Column('rainfall',      sa.Boolean(), nullable=True))
    op.add_column('sessions', sa.Column('wind_speed_ms', sa.Float(), nullable=True))

    # Also fix session_type check to include Sprint sessions
    op.drop_constraint('sessions_session_type_check', 'sessions', type_='check')
    op.create_check_constraint(
        'sessions_session_type_check',
        'sessions',
        "session_type = ANY (ARRAY['R','Q','FP1','FP2','FP3','S','SQ','SS'])"
    )


def downgrade() -> None:
    op.drop_column('sessions', 'track_temp_c')
    op.drop_column('sessions', 'air_temp_c')
    op.drop_column('sessions', 'humidity_pct')
    op.drop_column('sessions', 'rainfall')
    op.drop_column('sessions', 'wind_speed_ms')
