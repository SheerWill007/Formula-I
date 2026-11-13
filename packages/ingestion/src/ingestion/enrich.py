"""
Enrich sessions that are already in the database with the newer datasets
(results, track status, and, for races, OpenF1 gaps / positions / pit stops)
without re-ingesting laps or telemetry.

    uv run python -m ingestion.enrich --start-year 2022 --end-year 2025
    uv run python -m ingestion.enrich --year 2024 --dry-run

Idempotent: each loader replaces that session's rows, so re-running is safe.
"""

from __future__ import annotations

import argparse
import os

import structlog
from sqlalchemy import text

from ingestion.database import get_connection
from ingestion.fastf1_client import extract_session_results, extract_track_status
from ingestion.ingest_session import (
    NAME_TO_CODE,
    RACE_TIMING_SESSIONS,
    _ingest_race_timing,
)
from ingestion.loader import load_session_results, load_track_status

log = structlog.get_logger()


def _sessions_to_enrich(start_year: int, end_year: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT session_key, year, gp_name, session_name
                FROM sessions
                WHERE year BETWEEN :a AND :b
                ORDER BY year, date_start, session_key
                """
            ),
            {"a": start_year, "b": end_year},
        ).mappings()
        return [dict(r) for r in rows]


def enrich_session(row: dict) -> dict[str, int]:
    import fastf1

    cache_dir = os.environ.get("FASTF1_CACHE_DIR", "./fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)

    session = fastf1.get_session(row["year"], row["gp_name"], row["session_name"])
    # laps are needed to map timestamps to lap numbers; telemetry/weather are not.
    session.load(laps=True, telemetry=False, weather=False, messages=True)

    key = row["session_key"]
    out = {
        "results": load_session_results(extract_session_results(session, key), key),
        "track_status": load_track_status(extract_track_status(session, key), key),
    }
    if NAME_TO_CODE.get(row["session_name"]) in RACE_TIMING_SESSIONS:
        out.update(_ingest_race_timing(session, key))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill newer datasets")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--start-year", type=int, default=2022)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    start, end = (args.year, args.year) if args.year else (args.start_year, args.end_year)

    sessions = _sessions_to_enrich(start, end)
    log.info("enrich.plan", sessions=len(sessions), start=start, end=end)
    done = failed = 0
    for row in sessions:
        if args.dry_run:
            print(f"{row['year']} {row['gp_name']} / {row['session_name']}")
            continue
        try:
            counts = enrich_session(row)
            log.info("enrich.done", session_key=row["session_key"], **counts)
            done += 1
        except Exception as exc:
            log.error("enrich.failed", session_key=row["session_key"], error=str(exc))
            failed += 1
    log.info("enrich.finished", done=done, failed=failed)
    return 1 if failed and not done else 0


if __name__ == "__main__":
    raise SystemExit(main())
