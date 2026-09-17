"""Add WET to compound check constraint

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision      = '0007'
down_revision = '0006'
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.drop_constraint('lap_times_compound_check', 'lap_times', type_='check')
    op.create_check_constraint(
        'lap_times_compound_check',
        'lap_times',
        "compound IN ('SOFT','MEDIUM','HARD','INTER','INTERMEDIATE','WET','UNKNOWN')"
    )


def downgrade() -> None:
    op.drop_constraint('lap_times_compound_check', 'lap_times', type_='check')
    op.create_check_constraint(
        'lap_times_compound_check',
        'lap_times',
        "compound IN ('SOFT','MEDIUM','HARD','INTER','INTERMEDIATE','UNKNOWN')"
    )
