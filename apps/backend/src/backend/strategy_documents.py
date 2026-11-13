"""
Metadata and query helpers for strategy documents (Task 7).

Postgres is the source of truth for document metadata and chunks; the vector
store is only a rebuildable index. These helpers are read/write SQL against the
``strategy_documents`` and ``strategy_document_chunks`` tables. They contain no
HTTP and no Cloudflare awareness -- the vector adapter owns that.

Only rows whose ``permission_status`` is ``approved`` are ever returned for
retrieval or indexing.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from backend import extensions

APPROVED = "approved"


@dataclass(frozen=True)
class IndexableChunk:
    """A chunk that should be pushed to the vector store, with its metadata."""

    chunk_id: int
    document_id: int
    chunk_index: int
    text: str
    source_type: str
    title: str
    season: int | None
    session_key: int | None
    driver_number: int | None


@dataclass(frozen=True)
class StrategyChunkRecord:
    """A hydrated chunk join used to render source cards / citations."""

    chunk_id: int
    document_id: int
    chunk_index: int
    text: str
    source_type: str
    title: str
    source_url: str | None
    r2_key: str | None
    page_number: int | None
    lap_from: int | None
    lap_to: int | None
    timestamp_from_ms: int | None
    timestamp_to_ms: int | None
    season: int | None
    session_key: int | None
    driver_number: int | None
    team_name: str | None
    permission_status: str


def fetch_indexable_chunks(limit: int = 500) -> list[IndexableChunk]:
    """Approved chunks that are pending (or previously failed) indexing."""
    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.text,
                           d.source_type, d.title, d.season, d.session_key,
                           d.driver_number
                    FROM strategy_document_chunks c
                    JOIN strategy_documents d ON d.id = c.document_id
                    WHERE d.permission_status = :approved
                      AND c.index_status IN ('pending', 'failed')
                    ORDER BY c.document_id ASC, c.chunk_index ASC
                    LIMIT :lim
                    """
                ),
                {"approved": APPROVED, "lim": int(limit)},
            )
            .mappings()
            .all()
        )
    return [
        IndexableChunk(
            chunk_id=int(r["chunk_id"]),
            document_id=int(r["document_id"]),
            chunk_index=int(r["chunk_index"]),
            text=r["text"],
            source_type=r["source_type"],
            title=r["title"],
            season=r["season"],
            session_key=r["session_key"],
            driver_number=r["driver_number"],
        )
        for r in rows
    ]


def mark_chunks_indexed(pairs: list[tuple[int, str]]) -> int:
    """Record that chunk ids were indexed, storing their vector ids."""
    if not pairs:
        return 0
    with extensions.engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE strategy_document_chunks
                SET vector_id = :vector_id, index_status = 'indexed'
                WHERE id = :chunk_id
                """
            ),
            [{"chunk_id": cid, "vector_id": vid} for cid, vid in pairs],
        )
    return len(pairs)


def mark_chunks_status(chunk_ids: list[int], status: str) -> int:
    """Mark a set of chunks with a retryable status (e.g. 'failed')."""
    if not chunk_ids:
        return 0
    with extensions.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE strategy_document_chunks SET index_status = :status "
                "WHERE id = ANY(:ids)"
            ),
            {"status": status, "ids": list(chunk_ids)},
        )
    return len(chunk_ids)


def chunk_vector_ids(document_id: int) -> list[str]:
    """Every stored vector id belonging to a document (for deletion)."""
    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT vector_id FROM strategy_document_chunks "
                    "WHERE document_id = :doc AND vector_id IS NOT NULL"
                ),
                {"doc": document_id},
            )
            .scalars()
            .all()
        )
    return [r for r in rows if r]


def fetch_document(document_id: int) -> dict | None:
    with extensions.engine.connect() as conn:
        row = (
            conn.execute(
                text("SELECT * FROM strategy_documents WHERE id = :doc"),
                {"doc": document_id},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def fetch_documents_by_ids(document_ids: list[int]) -> dict[int, dict]:
    if not document_ids:
        return {}
    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text("SELECT * FROM strategy_documents WHERE id = ANY(:ids)"),
                {"ids": list(document_ids)},
            )
            .mappings()
            .all()
        )
    return {int(r["id"]): dict(r) for r in rows}


def hydrate_chunks(chunk_ids: list[int]) -> list[StrategyChunkRecord]:
    """Fetch chunk rows joined to their document, approved sources only."""
    if not chunk_ids:
        return []
    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.text,
                           c.page_number, c.lap_from, c.lap_to,
                           c.timestamp_from_ms, c.timestamp_to_ms,
                           d.source_type, d.title, d.source_url, d.r2_key,
                           d.season, d.session_key, d.driver_number, d.team_name,
                           d.permission_status
                    FROM strategy_document_chunks c
                    JOIN strategy_documents d ON d.id = c.document_id
                    WHERE c.id = ANY(:ids)
                      AND d.permission_status = :approved
                    """
                ),
                {"ids": list(chunk_ids), "approved": APPROVED},
            )
            .mappings()
            .all()
        )
    return [
        StrategyChunkRecord(
            chunk_id=int(r["chunk_id"]),
            document_id=int(r["document_id"]),
            chunk_index=int(r["chunk_index"]),
            text=r["text"],
            source_type=r["source_type"],
            title=r["title"],
            source_url=r["source_url"],
            r2_key=r["r2_key"],
            page_number=r["page_number"],
            lap_from=r["lap_from"],
            lap_to=r["lap_to"],
            timestamp_from_ms=r["timestamp_from_ms"],
            timestamp_to_ms=r["timestamp_to_ms"],
            season=r["season"],
            session_key=r["session_key"],
            driver_number=r["driver_number"],
            team_name=r["team_name"],
            permission_status=r["permission_status"],
        )
        for r in rows
    ]


def delete_document_chunks(document_id: int) -> int:
    with extensions.engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM strategy_document_chunks WHERE document_id = :doc"),
            {"doc": document_id},
        )
    return result.rowcount or 0
