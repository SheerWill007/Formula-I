"""Add Jolpica historical race and qualifying results

Revision ID: 0028
Revises: 0027
"""

from alembic import op
import sqlalchemy as sa


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Standalone from `sessions`: Jolpica covers 1950+, long before FastF1
    # session keys exist, so these rows are keyed by (year, round, kind, driver).
    op.create_table(
        "historical_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),  # 'R' race, 'Q' qualifying
        sa.Column("race_name", sa.Text(), nullable=True),
        sa.Column("circuit_id", sa.Text(), nullable=True),
        sa.Column("circuit_name", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("race_date", sa.Date(), nullable=True),
        sa.Column("driver_id", sa.Text(), nullable=False),
        sa.Column("driver_code", sa.Text(), nullable=True),
        sa.Column("driver_name", sa.Text(), nullable=True),
        sa.Column("constructor_id", sa.Text(), nullable=True),
        sa.Column("constructor_name", sa.Text(), nullable=True),
        sa.Column("grid", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("position_text", sa.Text(), nullable=True),
        sa.Column("points", sa.Float(), nullable=True),
        sa.Column("laps", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("q1", sa.Text(), nullable=True),
        sa.Column("q2", sa.Text(), nullable=True),
        sa.Column("q3", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "year", "round", "kind", "driver_id", name="uq_historical_results_row"
        ),
    )
    op.create_index("idx_historical_results_year", "historical_results", ["year", "round"])
    op.create_index("idx_historical_results_circuit", "historical_results", ["circuit_id"])
    op.create_index("idx_historical_results_driver", "historical_results", ["driver_id"])


def downgrade() -> None:
    op.drop_index("idx_historical_results_driver", "historical_results")
    op.drop_index("idx_historical_results_circuit", "historical_results")
    op.drop_index("idx_historical_results_year", "historical_results")
    op.drop_table("historical_results")
