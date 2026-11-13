"""
Fetch FIA PDFs (sporting/technical regulations, steward decisions) listed in a
manifest and feed them through the existing document pipeline
(``ingestion.documents``: extract -> chunk by page -> store -> index).

The manifest is a JSON list you maintain; this tool never scrapes the FIA site
and never guesses URLs:

    [
      {"url": "https://www.fia.com/.../2025_sporting_regs.pdf",
       "title": "2025 F1 Sporting Regulations",
       "source_type": "fia_regulation",
       "season": 2025},
      {"url": "https://www.fia.com/.../decision_doc_42.pdf",
       "title": "2025 Monaco GP, Doc 42: Decision",
       "source_type": "fia_decision",
       "season": 2025}
    ]

    uv run python -m ingestion.fia_documents --manifest fia.json --approve

FIA documents are copyrighted. The pipeline only indexes ``approved`` content,
so nothing is stored unless you pass ``--approve``, which is your statement
that you are allowed to use these documents for this purpose. Re-runs are
idempotent (documents are de-duplicated by content hash).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx
import structlog

from ingestion.documents import DocumentError, ingest_document

log = structlog.get_logger()

ALLOWED_SOURCE_TYPES = {"fia_regulation", "fia_decision", "fia_technical_directive"}
USER_AGENT = "slipstream-ingestion/0.1 (research; contact via repository)"
REQUEST_GAP_S = 1.5  # be polite to the host


def load_manifest(path: Path) -> list[dict]:
    items = json.loads(path.read_text())
    if not isinstance(items, list):
        raise DocumentError("manifest must be a JSON list")
    for i, item in enumerate(items):
        for field in ("url", "title", "source_type"):
            if not item.get(field):
                raise DocumentError(f"manifest item {i} is missing '{field}'")
        if item["source_type"] not in ALLOWED_SOURCE_TYPES:
            raise DocumentError(
                f"manifest item {i}: source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}"
            )
        if not str(item["url"]).lower().startswith("https://"):
            raise DocumentError(f"manifest item {i}: url must be https")
    return items


MAX_PDF_BYTES = 100 * 1024 * 1024  # generous for FIA regulations; stops runaway responses


def fetch_pdf(client: httpx.Client, url: str) -> bytes:
    """Download a PDF, refusing anything larger than ``MAX_PDF_BYTES``.

    The body is streamed so a huge or endless response cannot exhaust memory.
    """
    chunks: list[bytes] = []
    total = 0
    with client.stream("GET", url, follow_redirects=True, timeout=60) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_bytes():
            total += len(chunk)
            if total > MAX_PDF_BYTES:
                raise DocumentError(f"{url} is larger than {MAX_PDF_BYTES} bytes")
            chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        raise DocumentError(f"{url} did not return a PDF")
    return data


def ingest_manifest(items: list[dict], *, approve: bool) -> dict[str, int]:
    status = "approved" if approve else "pending"
    counts = {"created": 0, "duplicate": 0, "failed": 0}
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for item in items:
            try:
                data = fetch_pdf(client, item["url"])
                result = ingest_document(
                    source_type=item["source_type"],
                    title=item["title"],
                    data=data,
                    filename=Path(item["url"].split("?")[0]).name or "document.pdf",
                    mime_type="application/pdf",
                    permission_status=status,
                    source_url=item["url"],
                    season=item.get("season"),
                )
                counts["created" if result.created else "duplicate"] += 1
                log.info(
                    "fia.ingested",
                    title=item["title"],
                    chunks=result.chunk_count,
                    created=result.created,
                )
            except Exception as exc:
                counts["failed"] += 1
                log.error("fia.failed", title=item.get("title"), error=str(exc))
            time.sleep(REQUEST_GAP_S)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest FIA PDFs from a manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Confirm you may use these documents; without it nothing is stored",
    )
    args = parser.parse_args(argv)
    if not args.approve:
        # Without approval every item would be downloaded and then rejected.
        parser.error("--approve is required: FIA documents are copyrighted, see the module docstring")
    counts = ingest_manifest(load_manifest(args.manifest), approve=args.approve)
    print(json.dumps(counts))
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
