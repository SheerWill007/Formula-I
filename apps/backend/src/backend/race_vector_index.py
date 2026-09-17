"""
    LanceDB index for deterministic race-intelligence events.

    Postgres remains as the source of truth. Whereas, LanceDB is a rebuildable index for fast vector search of similarity index over the rows from race_intelligence_events.
"""

from __future__ import annotations
import hashlib
import json 
import math
import re
from typing import Any
from backend.config import settings

VECTOR_DIM = 384

def _connect():
    import lancedb
    return lancedb.connect(settings.race_vector_index_dir)

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())

def embed_text(text: str) -> list[float]:
    """ 
        Deterministic local embedding

        This is intentionally simple and dependency-light for the first LanceDB step.
        Later we can replace this with OpenAI embeddings or a local model while keeping
        the same LanceDB table shape.
    """
    vector = [0.0] * VECTOR_DIM
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % VECTOR_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[idx] += sign

    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    
    return [v / norm for v in vector]

def event_to_text(event: dict[str, Any]) -> str:
    payload = event.get("payload") or {}

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"raw": payload}

    parts = [
        f"event_type: {event.get('event_type')}",
        f"event_key: {event.get('event_key')}",
        f"driver_number: {event.get('driver_number')}",
        f"lap_number: {event.get('lap_number')}",
        f"payload: {json.dumps(payload, sort_keys=True)}",
    ]
    return "\n".join(parts)

def event_to_record(event: dict[str, Any]) -> dict[str, Any]:
    text = event_to_text(event)

    return {
        "id": int(event["id"]),
        "session_key": int(event["session_key"]),
        "event_type": event["event_type"],
        "event_key": event["event_key"],
        "driver_number": event.get("driver_number"),
        "lap_number": event.get("lap_number"),
        "text": text,
        "vector": embed_text(text),
        "payload_json": json.dumps(event.get("payload") or {}, sort_keys=True),
    }

def _table(records: list[dict[str, Any]] | None = None):
    db = _connect()
    table_name = settings.race_vector_table

    tables = db.list_tables()
    existing = set(tables.tables if hasattr(tables, "tables") else tables)
    if table_name in existing:
        return db.open_table(table_name)

    seed_records = records or [{
        "id": -1,
        "session_key": -1,
        "event_type": "seed",
        "event_key": "seed",
        "driver_number": None,
        "lap_number": None,
        "text": "seed",
        "vector": embed_text("seed"),
        "payload_json": "{}",
    }]
    return db.create_table(table_name, data=seed_records)

def rebuild_session_index(events: list[dict[str, Any]], session_key: int) -> int:
    records = [event_to_record(event) for event in events]
    table = _table(records)

    table.delete(f"session_key = {int(session_key)}")
    if records:
        table.add(records)

    return len(records)

def search_similar(query: str, limit: int = 8, event_type: str | None = None) -> list[dict[str, Any]]:
    table = _table()
    results = table.search(embed_text(query)).limit(limit).to_list()

    if event_type:
        results = [row for row in results if row.get("event_type") == event_type]

    cleaned = []
    for row in results[:limit]:
        payload_json = row.get("payload_json") or "{}"
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            payload = {}

        cleaned.append({
            "id": row.get("id"),
            "session_key": row.get("session_key"),
            "event_type": row.get("event_type"),
            "event_key": row.get("event_key"),
            "driver_number": row.get("driver_number"),
            "lap_number": row.get("lap_number"),
            "score": row.get("_distance"),
            "text": row.get("text"),
            "payload": payload,
        })

    return cleaned
