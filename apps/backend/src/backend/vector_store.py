"""
Vector store adapter (Task 8).

Only this module talks to Cloudflare Vectorize. Agent tools call these
functions, never Cloudflare directly. When Vectorize is not configured the
adapter uses a local LanceDB table for development so the rest of the system is
unchanged; production always uses Vectorize.

Contract:
- ``upsert_chunks(chunks) -> [(chunk_id, vector_id), ...]``
- ``search(query, filters, limit) -> [SearchHit, ...]``
- ``delete_document(document_id, vector_ids) -> int``

Metadata filters are applied BEFORE semantic ranking so a constrained question
never gets candidates from another session/driver.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from backend import embeddings, strategy_documents
from backend.config import settings
from backend.net import safe_urlopen


class VectorStoreError(Exception):
    """Raised when the vector store cannot be reached or used."""


@dataclass(frozen=True)
class SearchHit:
    chunk_id: int
    document_id: int
    score: float


def _vector_id(chunk_id: int) -> str:
    return f"strategy-chunk-{chunk_id}"


def is_configured() -> bool:
    """True when Cloudflare Vectorize credentials are present."""
    return bool(
        settings.cloudflare_account_id
        and settings.cloudflare_vectorize_api_token
        and settings.cloudflare_vectorize_index
    )


def _metadata(chunk: strategy_documents.IndexableChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "source_type": chunk.source_type,
        "season": chunk.season,
        "session_key": chunk.session_key,
        "driver_number": chunk.driver_number,
        # Belt-and-suspenders: retrieval re-checks this in Postgres too.
        "permission_status": strategy_documents.APPROVED,
    }


# --- Cloudflare Vectorize ----------------------------------------------------


def _vectorize_url(path: str) -> str:
    return (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.cloudflare_account_id}/vectorize/v2/indexes/"
        f"{settings.cloudflare_vectorize_index}/{path}"
    )


def _vectorize_request(path: str, payload, content_type: str = "application/json"):
    data = (
        payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    )
    request = urllib.request.Request(
        _vectorize_url(path),
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.cloudflare_vectorize_api_token}",
            "Content-Type": content_type,
        },
    )
    try:
        with safe_urlopen(
            request, timeout=settings.embedding_timeout_seconds
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VectorStoreError(f"Vectorize HTTP {exc.code}: {detail[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise VectorStoreError(f"Vectorize call failed: {exc}") from exc


def _vectorize_upsert(records: list[dict]) -> None:
    ndjson = "\n".join(json.dumps(record) for record in records).encode("utf-8")
    _vectorize_request("upsert", ndjson, content_type="application/x-ndjson")


def _vectorize_filter(filters: dict) -> dict:
    clauses: dict = {"permission_status": {"$eq": strategy_documents.APPROVED}}
    source_types = filters.get("source_types")
    if source_types:
        clauses["source_type"] = {"$in": list(source_types)}
    for key in ("season", "session_key", "driver_number"):
        value = filters.get(key)
        if value is not None:
            clauses[key] = {"$eq": int(value)}
    return clauses


def _vectorize_search(
    vector: list[float], filters: dict, limit: int
) -> list[SearchHit]:
    body = {
        "vector": vector,
        "topK": int(limit),
        "returnValues": False,
        "returnMetadata": "all",
        "filter": _vectorize_filter(filters),
    }
    payload = _vectorize_request("query", body)
    matches = (payload.get("result") or {}).get("matches") or []
    hits: list[SearchHit] = []
    for match in matches:
        meta = match.get("metadata") or {}
        chunk_id = meta.get("chunk_id")
        document_id = meta.get("document_id")
        if chunk_id is None or document_id is None:
            continue
        hits.append(
            SearchHit(
                chunk_id=int(chunk_id),
                document_id=int(document_id),
                score=float(match.get("score", 0.0)),
            )
        )
    return hits


# --- Local LanceDB fallback (development only) -------------------------------


def _local_table():
    import lancedb

    db = lancedb.connect(settings.race_vector_index_dir)
    table_name = settings.strategy_vector_table
    tables = db.list_tables()
    existing = set(tables.tables if hasattr(tables, "tables") else tables)
    if table_name in existing:
        return db.open_table(table_name)

    dims = embeddings.embedding_dimensions()
    seed = {
        "id": "seed",
        "chunk_id": -1,
        "document_id": -1,
        "source_type": "seed",
        "season": -1,
        "session_key": -1,
        "driver_number": -1,
        "permission_status": strategy_documents.APPROVED,
        "text": "seed",
        "vector": [0.0] * dims,
    }
    return db.create_table(table_name, data=[seed])


def _local_upsert(records: list[dict]) -> None:
    table = _local_table()
    for record in records:
        table.delete(f"id = '{record['id']}'")
    table.add(records)


def _local_search(vector: list[float], filters: dict, limit: int) -> list[SearchHit]:
    table = _local_table()
    clauses = [f"permission_status = '{strategy_documents.APPROVED}'"]
    source_types = filters.get("source_types")
    if source_types:
        quoted = ", ".join(f"'{s}'" for s in source_types)
        clauses.append(f"source_type IN ({quoted})")
    for key in ("season", "session_key", "driver_number"):
        value = filters.get(key)
        if value is not None:
            clauses.append(f"{key} = {int(value)}")
    query = table.search(vector).where(" AND ".join(clauses), prefilter=True)
    rows = query.limit(int(limit)).to_list()
    hits: list[SearchHit] = []
    for row in rows:
        if int(row.get("chunk_id", -1)) < 0:
            continue
        distance = float(row.get("_distance", 0.0))
        hits.append(
            SearchHit(
                chunk_id=int(row["chunk_id"]),
                document_id=int(row["document_id"]),
                score=1.0 / (1.0 + distance),
            )
        )
    return hits


# --- Public API --------------------------------------------------------------


def upsert_chunks(
    chunks: list[strategy_documents.IndexableChunk],
) -> list[tuple[int, str]]:
    """Embed and store chunks, returning their (chunk_id, vector_id) pairs."""
    if not chunks:
        return []
    try:
        vectors = embeddings.embed_texts([c.text for c in chunks])
    except embeddings.EmbeddingError as exc:
        raise VectorStoreError(str(exc)) from exc

    records = [
        {
            "id": _vector_id(chunk.chunk_id),
            "values": vector,
            "metadata": _metadata(chunk),
        }
        for chunk, vector in zip(chunks, vectors)
    ]
    if is_configured():
        _vectorize_upsert(records)
    else:
        local_records = [
            {
                "id": record["id"],
                **record["metadata"],
                "text": chunk.text,
                "vector": record["values"],
            }
            for record, chunk in zip(records, chunks)
        ]
        _local_upsert(local_records)
    return [(chunk.chunk_id, _vector_id(chunk.chunk_id)) for chunk in chunks]


def delete_document(document_id: int, vector_ids: list[str]) -> int:
    """Remove every vector belonging to a document."""
    if is_configured():
        if not vector_ids:
            return 0
        _vectorize_request("delete", {"ids": vector_ids})
        return len(vector_ids)
    table = _local_table()
    table.delete(f"document_id = {int(document_id)}")
    return len(vector_ids)


def search(
    query: str,
    *,
    source_types: list[str] | None = None,
    year: int | None = None,
    session_key: int | None = None,
    driver_number: int | None = None,
    limit: int | None = None,
) -> list[SearchHit]:
    """Semantic search with metadata filters applied before ranking."""
    cleaned = query.strip()
    if not cleaned:
        raise VectorStoreError("query must be non-empty")
    limit = int(limit or settings.strategy_retrieval_limit)
    filters = {
        "source_types": source_types,
        "season": year,
        "session_key": session_key,
        "driver_number": driver_number,
    }
    try:
        vector = embeddings.embed_text(cleaned)
    except embeddings.EmbeddingError as exc:
        raise VectorStoreError(str(exc)) from exc

    if is_configured():
        return _vectorize_search(vector, filters, limit)
    return _local_search(vector, filters, limit)


def reindex_pending_chunks(limit: int = 500) -> dict:
    """Embed pending/failed approved chunks into the vector store.

    On failure every chunk in the batch is marked 'failed' (retryable) and the
    error is re-raised so a worker can retry the job.
    """
    chunks = strategy_documents.fetch_indexable_chunks(limit=limit)
    if not chunks:
        return {"indexed": 0, "chunks": 0}
    try:
        pairs = upsert_chunks(chunks)
    except Exception:
        strategy_documents.mark_chunks_status([c.chunk_id for c in chunks], "failed")
        raise
    strategy_documents.mark_chunks_indexed(pairs)
    return {"indexed": len(pairs), "chunks": len(chunks)}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Reindex pending strategy chunks")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)
    result = reindex_pending_chunks(limit=args.limit)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
