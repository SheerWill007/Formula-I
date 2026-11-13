"""Task 8: embeddings, vector store adapter, and search_strategy_sources."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text

from backend import embeddings, strategy_documents, vector_store
from backend.agent import orchestrator, tools, types
from backend.config import settings


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _insert_document(
    db_engine,
    *,
    sha: str,
    chunk_text: str,
    permission: str = "approved",
    session_key: int | None = 99999,
    driver_number: int | None = 44,
    source_type: str = "race_director",
    title: str = "RD notes",
    timestamp_from_ms: int | None = None,
) -> int:
    with db_engine.begin() as conn:
        document_id = conn.execute(
            text(
                """
                INSERT INTO strategy_documents (
                    source_type, title, r2_key, sha256, mime_type, season,
                    session_key, driver_number, permission_status
                ) VALUES (
                    :st, :title, :rk, :sha, 'text/plain', 2026,
                    :sk, :dn, :perm
                ) RETURNING id
                """
            ),
            {
                "st": source_type,
                "title": title,
                "rk": f"strategy_documents/{sha}.txt",
                "sha": sha,
                "sk": session_key,
                "dn": driver_number,
                "perm": permission,
            },
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO strategy_document_chunks (
                    document_id, chunk_index, text, timestamp_from_ms, index_status
                ) VALUES (:doc, 0, :txt, :ts, 'pending')
                """
            ),
            {"doc": document_id, "txt": chunk_text, "ts": timestamp_from_ms},
        )
    return int(document_id)


def _cleanup(db_engine, shas: list[str]) -> None:
    if not shas:
        return
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM strategy_documents WHERE sha256 = ANY(:shas)"),
            {"shas": shas},
        )


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "race_vector_index_dir", str(tmp_path))
    return tmp_path


def test_embedding_dimension_matches_config():
    vector = embeddings.embed_text("safety car pit loss")
    assert len(vector) == settings.embedding_dimensions


def test_search_returns_hits_with_filters_and_timestamps(
    app, db_engine, seed_session, isolated_store
):
    sha_a = _sha("doc-a")
    sha_b = _sha("doc-b")
    doc_a = _insert_document(
        db_engine,
        sha=sha_a,
        chunk_text="the safety car procedure alpha requires pit lane closure",
        timestamp_from_ms=12345,
    )
    doc_b = _insert_document(
        db_engine,
        sha=sha_b,
        chunk_text="tyre blanket temperatures beta for the next event",
        session_key=99999,
        driver_number=63,
    )
    try:
        result = vector_store.reindex_pending_chunks()
        assert result["indexed"] >= 2

        hits = tools.search_strategy_sources(
            types.SearchStrategySourcesInput(
                query="safety car procedure alpha",
                session_key=99999,
                driver_number=44,
                limit=5,
            )
        ).hits
        assert hits, "expected at least one source hit"
        assert {h.document_id for h in hits} == {doc_a}
        assert hits[0].timestamp_from_ms == 12345

        other = tools.search_strategy_sources(
            types.SearchStrategySourcesInput(
                query="tyre blanket beta",
                session_key=99999,
                driver_number=63,
                limit=5,
            )
        ).hits
        assert {h.document_id for h in other} == {doc_b}
    finally:
        _cleanup(db_engine, [sha_a, sha_b])


def test_unapproved_chunk_is_never_displayed(
    app, db_engine, seed_session, isolated_store
):
    sha = _sha("pending-doc")
    document_id = _insert_document(
        db_engine,
        sha=sha,
        chunk_text="unapproved secret strategy delta",
        permission="pending",
    )
    try:
        # Force the chunk into the vector store anyway; hydration must drop it.
        vector_store.upsert_chunks(
            [
                strategy_documents.IndexableChunk(
                    chunk_id=document_id,
                    document_id=document_id,
                    chunk_index=0,
                    text="unapproved secret strategy delta",
                    source_type="race_director",
                    title="RD notes",
                    season=2026,
                    session_key=99999,
                    driver_number=44,
                )
            ]
        )
        result = tools.search_strategy_sources(
            types.SearchStrategySourcesInput(query="unapproved secret strategy delta")
        )
        assert all(hit.document_id != document_id for hit in result.hits)
    finally:
        _cleanup(db_engine, [sha])


def test_retrieval_failure_degrades_without_raising(app, monkeypatch):
    def _boom(*args, **kwargs):
        raise vector_store.VectorStoreError("vectorize down")

    monkeypatch.setattr(vector_store, "search", _boom)
    result = tools.search_strategy_sources(
        types.SearchStrategySourcesInput(query="any regulation question")
    )
    assert result.degraded is True
    assert result.hits == ()
    assert result.note and "unavailable" in result.note


def test_telemetry_intents_do_not_run_rag():
    telemetry = orchestrator.build_dag(
        types.RoutedQuestion(
            intent=types.Intent.TELEMETRY_COMPARISON,
            question="compare laps",
            driver_name="HAM",
            compare_driver_name="RUS",
            gp_name="Monza",
            year=2026,
            target_lap=10,
        )
    )
    strategy = orchestrator.build_dag(
        types.RoutedQuestion(
            intent=types.Intent.STRATEGY_ANALYSIS,
            question="should he pit",
            driver_name="HAM",
            gp_name="Monza",
            year=2026,
        )
    )
    for dag in (telemetry, strategy):
        assert types.ToolName.SEARCH_STRATEGY_SOURCES not in {
            n.tool_name for n in dag.nodes
        }

    sources = orchestrator.build_dag(
        types.RoutedQuestion(
            intent=types.Intent.STRATEGY_SOURCES,
            question="what do the regulations say about safety car pit stops",
        )
    )
    assert types.ToolName.SEARCH_STRATEGY_SOURCES in {
        n.tool_name for n in sources.nodes
    }


def test_reindex_marks_chunks_indexed(app, db_engine, seed_session, isolated_store):
    sha = _sha("reindex-doc")
    document_id = _insert_document(
        db_engine, sha=sha, chunk_text="green flag pit window regulation gamma"
    )
    try:
        vector_store.reindex_pending_chunks()
        with db_engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT id, index_status, vector_id FROM strategy_document_chunks "
                        "WHERE document_id = :doc"
                    ),
                    {"doc": document_id},
                )
                .mappings()
                .one()
            )
        assert row["index_status"] == "indexed"
        assert row["vector_id"] == f"strategy-chunk-{row['id']}"
    finally:
        _cleanup(db_engine, [sha])
