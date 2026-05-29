
"""Add lap_telemetry_stats table

Revision ID: 0008

Revises: 0007

"""

from alembic import op

import sqlalchemy as sa

from sqlalchemy.dialects.postgresql import JSONB

revision      = '0008'

down_revision = '0007'

branch_labels = None

depends_on    = None

def upgrade() -> None:

    op.create_table(

        'lap_telemetry_stats',

        sa.Column('id',            sa.Integer(), primary_key=True),

        sa.Column('session_key',   sa.Integer(), nullable=False),

        sa.Column('driver_number', sa.Integer(), nullable=False),

        sa.Column('lap_number',    sa.Integer(), nullable=False),

        sa.Column('corners',       JSONB),

        sa.Column('speed_trap_1_kmh',    sa.Float()),

        sa.Column('speed_trap_2_kmh',    sa.Float()),

        sa.Column('max_speed_kmh',       sa.Float()),

        sa.Column('max_rpm',             sa.Integer()),

        sa.Column('avg_rpm_pct',         sa.Float()),

        sa.Column('avg_brake_point_pct', sa.Float()),

        sa.Column('drs_open_pct',        sa.Float()),

        sa.Column('computed_at', sa.TIMESTAMP(timezone=True),

                  nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(['session_key'], ['sessions.session_key']),

        sa.UniqueConstraint('session_key', 'driver_number', 'lap_number',

                            name='uq_lap_tel_stats'),

    )

    op.create_index('idx_lap_tel_stats_session', 'lap_telemetry_stats',

                    ['session_key', 'driver_number'])

def downgrade() -> None:

    op.drop_index('idx_lap_tel_stats_session', 'lap_telemetry_stats')

    op.drop_table('lap_telemetry_stats')

