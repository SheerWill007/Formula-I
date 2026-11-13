"""Task 7: strategy document ingestion, chunking, and traceability."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from ingestion import documents


def _cleanup(db_engine, sha256: str) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM strategy_documents WHERE sha256 = :sha"), {"sha": sha256}
        )


def test_chunk_segments_has_overlap():
    segments = [documents.ExtractedSegment(text="a b c d e f g h")]
    chunks = documents.chunk_segments(segments, max_tokens=3, overlap_tokens=1)
    texts = [c.text for c in chunks]
    assert texts[0] == "a b c"
    assert texts[1] == "c d e"  # overlaps the previous window
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.token_count <= 3 for c in chunks)


def test_transcript_timestamps_are_preserved():
    payload = json.dumps(
        [
            {"text": "box this lap", "timestamp_ms": 1000},
            {"text": "stay out", "timestamp_ms": 4500},
        ]
    ).encode()
    segments = documents.extract_segments(payload, "application/json")
    assert [s.timestamp_from_ms for s in segments] == [1000, 4500]
    chunks = documents.chunk_segments(segments, max_tokens=10, overlap_tokens=0)
    assert chunks[0].timestamp_from_ms == 1000
    assert chunks[1].timestamp_from_ms == 4500


def test_unsupported_mime_type_rejected():
    with pytest.raises(documents.DocumentError):
        documents.extract_segments(b"\x00\x01", "application/octet-stream")


def test_unapproved_document_is_never_stored(db_engine):
    with pytest.raises(documents.DocumentError):
        documents.ingest_document(
            source_type="regulation",
            title="Secret notes",
            data=b"confidential strategy content that must not be indexed",
            permission_status="pending",
        )
    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM strategy_documents WHERE title = 'Secret notes'")
        ).scalar()
    assert count == 0


def test_approved_document_is_traceable_and_idempotent(
    db_engine, seed_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(documents.settings, "strategy_document_dir", str(tmp_path))
    monkeypatch.setattr(documents.settings, "strategy_document_backend", "local")
    body = f"Race director note {tmp_path}".encode()

    try:
        first = documents.ingest_document(
            source_type="race_director",
            title="RD notes",
            data=body,
            filename="rd.txt",
            permission_status="approved",
            season=2026,
            session_key=99999,
            driver_number=44,
        )
        assert first.created is True
        assert first.chunk_count >= 1
        # Traceable: R2/local key stored and the original bytes exist on disk.
        assert first.r2_key
        assert (tmp_path / first.r2_key).exists()

        with db_engine.connect() as conn:
            doc = (
                conn.execute(
                    text("SELECT * FROM strategy_documents WHERE id = :id"),
                    {"id": first.document_id},
                )
                .mappings()
                .one()
            )
            chunk_rows = (
                conn.execute(
                    text(
                        "SELECT chunk_index, index_status FROM strategy_document_chunks "
                        "WHERE document_id = :id ORDER BY chunk_index"
                    ),
                    {"id": first.document_id},
                )
                .mappings()
                .all()
            )
        assert doc["permission_status"] == "approved"
        assert doc["sha256"] == first.sha256
        assert len(chunk_rows) == first.chunk_count
        assert {c["index_status"] for c in chunk_rows} == {"pending"}

        # Re-ingesting identical bytes duplicates nothing.
        second = documents.ingest_document(
            source_type="race_director",
            title="RD notes",
            data=body,
            filename="rd.txt",
            permission_status="approved",
        )
        assert second.created is False
        assert second.chunk_count == 0
        assert second.document_id == first.document_id

        with db_engine.connect() as conn:
            total = conn.execute(
                text("SELECT COUNT(*) FROM strategy_documents WHERE sha256 = :sha"),
                {"sha": first.sha256},
            ).scalar()
        assert total == 1
    finally:
        _cleanup(db_engine, documents.sha256_of(body))
