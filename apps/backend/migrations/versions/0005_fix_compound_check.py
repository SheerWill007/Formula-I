"""Fix compound check constraint to include INTERMEDIATE

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision      = '0005'
down_revision = '0003'
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
        "compound IN ('SOFT','MEDIUM','HARD','INTER','WET')"
    )
