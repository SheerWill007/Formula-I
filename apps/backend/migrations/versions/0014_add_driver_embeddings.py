"""Add driver_embeddings table for PCA embedding pipeline

Revision ID: 0014
Revises: 0013
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "driver_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver_number", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("abbreviation", sa.Text(), nullable=False),
        sa.Column("team_name", sa.Text(), nullable=True),
        # PCA embedding — N-dim vector stored as PostgreSQL array
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=False),
        # Explained variance per component — how much info each dim holds
        sa.Column("pca_explained_variance", sa.ARRAY(sa.Float()), nullable=False),
        # JSONB mapping each component to its top contributing features
        sa.Column("pca_loadings", sa.JSON(), nullable=False),
        sa.Column(
            "computed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "driver_number", "season", name="uq_driver_embeddings_driver_season"
        ),
    )

    op.create_index(
        "idx_driver_embeddings_season",
        "driver_embeddings",
        ["season"],
    )


def downgrade() -> None:
    op.drop_index("idx_driver_embeddings_season", "driver_embeddings")
    op.drop_table("driver_embeddings")
