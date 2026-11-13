"""
Strategy-document ingestion: extraction, chunking, and the one-shot loader.

Task 7 (R2 documents/transcripts). The workflow is deliberately split so no
heavy parsing ever happens inside an HTTP request:

1. Upload the original file/audio/transcript to R2 (or the local artifact dir).
2. Write the metadata record in PostgreSQL.
3. Extract text here, in a one-shot CLI/worker job.
4. Chunk by section with overlap; preserve PDF pages and transcript timestamps.
5. Hash the source content for idempotency; re-ingesting identical input
   duplicates neither the document nor its chunks.
6. Only ``approved`` content is ever stored/indexed -- unapproved input is
   rejected before a row is written.

Run it:

    python -m ingestion.documents --path notes.pdf \\
        --source-type engineering_note --title "Race 5 debrief" \\
        --permission-status approved --season 2026
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from ingestion.config import settings
from ingestion.database import get_connection

import structlog

log = structlog.get_logger()

APPROVED = "approved"

# Word-based token approximation: no tokenizer dependency, stable across runs.
DEFAULT_MAX_TOKENS = 220
DEFAULT_OVERLAP_TOKENS = 40

_TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/csv",
}
_JSON_MIME_TYPES = {"application/json", "text/json"}


class DocumentError(Exception):
    """Raised when a document cannot be extracted, chunked, or stored."""


@dataclass(frozen=True)
class ExtractedSegment:
    """One contiguous unit of text: a PDF page, a transcript line, a section."""

    text: str
    page_number: int | None = None
    timestamp_from_ms: int | None = None
    timestamp_to_ms: int | None = None


@dataclass(frozen=True)
class ChunkDraft:
    """A ready-to-store chunk with all provenance preserved."""

    chunk_index: int
    text: str
    token_count: int
    page_number: int | None = None
    timestamp_from_ms: int | None = None
    timestamp_to_ms: int | None = None


@dataclass(frozen=True)
class IngestResult:
    document_id: int
    chunk_count: int
    created: bool
    sha256: str
    title: str
    r2_key: str | None = None
    chunks: tuple[ChunkDraft, ...] = field(default_factory=tuple)


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _count_tokens(text: str) -> int:
    return len(text.split())


def _guess_mime_type(filename: str, mime_type: str | None) -> str:
    if mime_type:
        return mime_type
    suffix = Path(filename).suffix.lower()
    return {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".json": "application/json",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
    }.get(suffix, "application/octet-stream")


def _coerce_ms(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return int(raw)
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    return None


def _transcript_segments(payload) -> list[ExtractedSegment]:
    """Best-effort transcript parsing: list of {text, timestamp_ms/date}."""
    entries = None
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        for key in ("segments", "transcript", "utterances", "messages", "items"):
            if isinstance(payload.get(key), list):
                entries = payload[key]
                break

    segments: list[ExtractedSegment] = []
    if entries is not None:
        for entry in entries:
            if isinstance(entry, str):
                if entry.strip():
                    segments.append(ExtractedSegment(text=entry.strip()))
                continue
            if not isinstance(entry, dict):
                continue
            raw_text = (
                entry.get("text")
                or entry.get("transcript")
                or entry.get("message")
                or entry.get("content")
                or ""
            )
            cleaned = str(raw_text).strip()
            if not cleaned:
                continue
            start = _coerce_ms(
                entry.get("timestamp_ms")
                or entry.get("start_ms")
                or entry.get("start")
                or entry.get("date")
                or entry.get("timestamp")
            )
            end = _coerce_ms(entry.get("timestamp_to_ms") or entry.get("end_ms"))
            segments.append(
                ExtractedSegment(
                    text=cleaned,
                    timestamp_from_ms=start,
                    timestamp_to_ms=end if end is not None else start,
                )
            )
    return segments


def _extract_pdf(data: bytes) -> list[ExtractedSegment]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DocumentError(
            "PDF extraction requires the optional 'pypdf' package"
        ) from exc

    reader = PdfReader(io.BytesIO(data))
    segments: list[ExtractedSegment] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            segments.append(ExtractedSegment(text=page_text, page_number=page_number))
    return segments


def extract_segments(data: bytes, mime_type: str) -> list[ExtractedSegment]:
    """Turn raw bytes into ordered text segments, preserving provenance."""
    if mime_type == "application/pdf":
        return _extract_pdf(data)

    if mime_type in _JSON_MIME_TYPES:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DocumentError(f"invalid JSON document: {exc}") from exc
        segments = _transcript_segments(payload)
        if segments:
            return segments
        # Not a recognisable transcript: fall back to the pretty-printed body.
        return [ExtractedSegment(text=json.dumps(payload, indent=2, sort_keys=True))]

    if mime_type in _TEXT_MIME_TYPES or mime_type.startswith("text/"):
        try:
            text_body = data.decode("utf-8", errors="replace")
        except Exception as exc:  # pragma: no cover - decode is defensive
            raise DocumentError(f"could not decode text document: {exc}") from exc
        cleaned = text_body.strip()
        return [ExtractedSegment(text=cleaned)] if cleaned else []

    raise DocumentError(f"Unsupported mime type for extraction: {mime_type}")


def chunk_segments(
    segments: list[ExtractedSegment],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    """Chunk each segment with a sliding word window and overlap.

    Chunking stays inside a segment so a chunk never blends two PDF pages or
    two transcript timestamps; overlap preserves context across window edges.
    """
    if max_tokens <= 0:
        raise DocumentError("max_tokens must be positive")
    overlap = max(0, min(overlap_tokens, max_tokens - 1))
    step = max_tokens - overlap

    chunks: list[ChunkDraft] = []
    index = 0
    for segment in segments:
        words = segment.text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            window = words[start : start + max_tokens]
            text_body = " ".join(window).strip()
            if text_body:
                chunks.append(
                    ChunkDraft(
                        chunk_index=index,
                        text=text_body,
                        token_count=len(window),
                        page_number=segment.page_number,
                        timestamp_from_ms=segment.timestamp_from_ms,
                        timestamp_to_ms=segment.timestamp_to_ms,
                    )
                )
                index += 1
            if start + max_tokens >= len(words):
                break
            start += step
    return chunks


# --- Object storage (R2 or local dir), mirrors the telemetry artifact path ---


def _document_backend() -> str:
    backend = settings.strategy_document_backend.strip().lower()
    return backend if backend in {"local", "r2"} else "local"


def _document_bucket() -> str:
    return settings.strategy_document_bucket or settings.telemetry_artifact_bucket


def _r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def document_storage_key(source_type: str, sha256: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"strategy_documents/{source_type}/{sha256}{suffix}"


def upload_document(data: bytes, key: str, content_type: str) -> str:
    """Store the original bytes and return the storage key."""
    if _document_backend() == "r2":
        bucket = _document_bucket()
        if not bucket:
            raise DocumentError("strategy_document bucket is not configured for R2")
        _r2_client().put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type
        )
    else:
        path = Path(settings.strategy_document_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return key


def download_document(key: str) -> bytes:
    """Fetch the original bytes back from storage."""
    if _document_backend() == "r2":
        bucket = _document_bucket()
        if not bucket:
            raise DocumentError("strategy_document bucket is not configured for R2")
        obj = _r2_client().get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    path = Path(settings.strategy_document_dir) / key
    if not path.exists():
        raise DocumentError(f"document file not found: {path}")
    return path.read_bytes()


# --- Ingestion orchestration -------------------------------------------------


def _existing_document_id(conn, sha256: str) -> int | None:
    return conn.execute(
        text("SELECT id FROM strategy_documents WHERE sha256 = :sha"),
        {"sha": sha256},
    ).scalar()


def ingest_document(
    *,
    source_type: str,
    title: str,
    data: bytes,
    filename: str = "",
    mime_type: str | None = None,
    permission_status: str = "pending",
    r2_key: str | None = None,
    source_url: str | None = None,
    season: int | None = None,
    session_key: int | None = None,
    driver_number: int | None = None,
    team_name: str | None = None,
    published_at=None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    upload: bool = True,
) -> IngestResult:
    """Extract, chunk, and store one document. Idempotent by content hash."""
    if permission_status != APPROVED:
        raise DocumentError(
            f"refusing to ingest content with permission_status="
            f"'{permission_status}'; only '{APPROVED}' sources may be indexed"
        )
    if not title.strip():
        raise DocumentError("title is required")
    if not source_type.strip():
        raise DocumentError("source_type is required")

    resolved_mime = _guess_mime_type(filename or title, mime_type)
    digest = sha256_of(data)

    with get_connection() as conn:
        existing_id = _existing_document_id(conn, digest)
        if existing_id is not None:
            log.info(
                "documents.ingest.duplicate", document_id=existing_id, sha256=digest
            )
            return IngestResult(
                document_id=int(existing_id),
                chunk_count=0,
                created=False,
                sha256=digest,
                title=title,
            )

        segments = extract_segments(data, resolved_mime)
        chunks = chunk_segments(segments, max_tokens, overlap_tokens)
        if not chunks:
            raise DocumentError("extraction produced no text to chunk")

        storage_key = r2_key
        if storage_key is None and upload:
            storage_key = document_storage_key(source_type, digest, filename or title)
            upload_document(data, storage_key, resolved_mime)

        document_id = conn.execute(
            text(
                """
                INSERT INTO strategy_documents (
                    source_type, title, r2_key, source_url, sha256, mime_type,
                    season, session_key, driver_number, team_name,
                    published_at, permission_status
                ) VALUES (
                    :source_type, :title, :r2_key, :source_url, :sha256, :mime_type,
                    :season, :session_key, :driver_number, :team_name,
                    :published_at, :permission_status
                )
                RETURNING id
                """
            ),
            {
                "source_type": source_type,
                "title": title,
                "r2_key": storage_key,
                "source_url": source_url,
                "sha256": digest,
                "mime_type": resolved_mime,
                "season": season,
                "session_key": session_key,
                "driver_number": driver_number,
                "team_name": team_name,
                "published_at": published_at,
                "permission_status": permission_status,
            },
        ).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO strategy_document_chunks (
                    document_id, chunk_index, text, page_number,
                    timestamp_from_ms, timestamp_to_ms, token_count, index_status
                ) VALUES (
                    :document_id, :chunk_index, :text, :page_number,
                    :timestamp_from_ms, :timestamp_to_ms, :token_count, 'pending'
                )
                """
            ),
            [
                {
                    "document_id": document_id,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "page_number": chunk.page_number,
                    "timestamp_from_ms": chunk.timestamp_from_ms,
                    "timestamp_to_ms": chunk.timestamp_to_ms,
                    "token_count": chunk.token_count,
                }
                for chunk in chunks
            ],
        )

    log.info(
        "documents.ingest.done",
        document_id=document_id,
        chunks=len(chunks),
        source_type=source_type,
        r2_key=storage_key,
    )
    return IngestResult(
        document_id=int(document_id),
        chunk_count=len(chunks),
        created=True,
        sha256=digest,
        title=title,
        r2_key=storage_key,
        chunks=tuple(chunks),
    )


def ingest_from_r2(
    r2_key: str,
    *,
    source_type: str,
    title: str,
    filename: str = "",
    mime_type: str | None = None,
    permission_status: str = "pending",
    **kwargs,
) -> IngestResult:
    """Download an already-uploaded object, then ingest it (no re-upload)."""
    data = download_document(r2_key)
    return ingest_document(
        source_type=source_type,
        title=title,
        data=data,
        filename=filename or r2_key,
        mime_type=mime_type,
        permission_status=permission_status,
        r2_key=r2_key,
        upload=False,
        **kwargs,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest a strategy document")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", type=str, help="Local file to upload and ingest")
    source.add_argument(
        "--r2-key", type=str, help="Object already stored in R2/local storage"
    )
    parser.add_argument("--source-type", type=str, required=True)
    parser.add_argument("--title", type=str, required=True)
    parser.add_argument("--mime-type", type=str, default=None)
    parser.add_argument("--source-url", type=str, default=None)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--session-key", type=int, default=None)
    parser.add_argument("--driver-number", type=int, default=None)
    parser.add_argument("--team-name", type=str, default=None)
    parser.add_argument(
        "--permission-status", type=str, default="pending", help="approved|pending|..."
    )
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    common = dict(
        source_type=args.source_type,
        title=args.title,
        mime_type=args.mime_type,
        permission_status=args.permission_status,
        source_url=args.source_url,
        season=args.season,
        session_key=args.session_key,
        driver_number=args.driver_number,
        team_name=args.team_name,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )

    if args.path:
        filename = Path(args.path).name
        data = Path(args.path).read_bytes()
        result = ingest_document(data=data, filename=filename, **common)
    else:
        result = ingest_from_r2(args.r2_key, filename=args.r2_key, **common)

    print(
        json.dumps(
            {
                "document_id": result.document_id,
                "chunks": result.chunk_count,
                "created": result.created,
                "sha256": result.sha256,
                "r2_key": result.r2_key,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
