"""Add circuit_embeddings table for learned circuit representations

Revision ID: 0018
Revises: 0017
"""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "circuit_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("circuit_key", sa.Integer(), nullable=False),
        sa.Column("gp_name", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=True),
        # PCA embedding — N-dim vector
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=False),
        sa.Column("pca_explained_variance", sa.ARRAY(sa.Float()), nullable=False),
        sa.Column("pca_loadings", sa.JSON(), nullable=False),
        sa.Column("axis_labels", sa.JSON(), nullable=True),
        # Circuit metadata for display
        sa.Column("n_races", sa.Integer(), nullable=True),
        sa.Column("avg_lap_time_ms", sa.Float(), nullable=True),
        sa.Column("n_corners_avg", sa.Float(), nullable=True),
        sa.Column(
            "computed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("circuit_key", name="uq_circuit_embeddings_key"),
    )

    op.create_index(
        "idx_circuit_embeddings_gp",
        "circuit_embeddings",
        ["gp_name"],
    )


def downgrade() -> None:
    op.drop_index("idx_circuit_embeddings_gp", "circuit_embeddings")
    op.drop_table("circuit_embeddings")
