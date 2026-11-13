"""Add strategy documents and chunks storage (Task 7)

Revision ID: 0025
Revises: 0024
"""

from alembic import op
import sqlalchemy as sa


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("r2_key", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("session_key", sa.Integer(), nullable=True),
        sa.Column("driver_number", sa.Integer(), nullable=True),
        sa.Column("team_name", sa.Text(), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "permission_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["session_key"], ["sessions.session_key"]),
    )
    # Idempotency: identical source content can only be ingested once.
    op.create_unique_constraint(
        "uq_strategy_documents_sha256", "strategy_documents", ["sha256"]
    )
    op.create_index(
        "idx_strategy_documents_session", "strategy_documents", ["session_key"]
    )
    op.create_index("idx_strategy_documents_season", "strategy_documents", ["season"])
    op.create_index(
        "idx_strategy_documents_source_type", "strategy_documents", ["source_type"]
    )
    op.create_index(
        "idx_strategy_documents_permission",
        "strategy_documents",
        ["permission_status"],
    )

    op.create_table(
        "strategy_document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("lap_from", sa.Integer(), nullable=True),
        sa.Column("lap_to", sa.Integer(), nullable=True),
        sa.Column("timestamp_from_ms", sa.BigInteger(), nullable=True),
        sa.Column("timestamp_to_ms", sa.BigInteger(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("vector_id", sa.Text(), nullable=True),
        sa.Column("index_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["strategy_documents.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_strategy_chunk_document_index"
        ),
    )
    op.create_index(
        "idx_strategy_chunks_document", "strategy_document_chunks", ["document_id"]
    )
    op.create_index(
        "idx_strategy_chunks_index_status",
        "strategy_document_chunks",
        ["index_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_strategy_chunks_index_status", "strategy_document_chunks")
    op.drop_index("idx_strategy_chunks_document", "strategy_document_chunks")
    op.drop_table("strategy_document_chunks")
    op.drop_index("idx_strategy_documents_permission", "strategy_documents")
    op.drop_index("idx_strategy_documents_source_type", "strategy_documents")
    op.drop_index("idx_strategy_documents_season", "strategy_documents")
    op.drop_index("idx_strategy_documents_session", "strategy_documents")
    op.drop_constraint(
        "uq_strategy_documents_sha256", "strategy_documents", type_="unique"
    )
    op.drop_table("strategy_documents")
