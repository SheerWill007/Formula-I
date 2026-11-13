"""
Backfill historical F1 sessions into the database.

Unlike ``auto_ingest`` (current season only), this walks an arbitrary range of
years, reads each event's *actual* sessions from the FastF1 schedule — so it
handles the 2022/2023 sprint format ("Sprint Shootout") as well as the modern
"Sprint Qualifying" — and ingests any session that has completed but is not yet
in the database.

Resumable: already-ingested sessions are skipped, so a timed-out job can simply
be re-run.

Run manually:
    uv run python -m ingestion.backfill --start-year 2022 --end-year 2025
    uv run python -m ingestion.backfill --start-year 2024 --end-year 2024 --skip-telemetry
    uv run python -m ingestion.backfill --start-year 2022 --end-year 2025 --dry-run
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import structlog
from sqlalchemy import create_engine

from ingestion.config import settings
from ingestion.auto_ingest import get_ingested_sessions
from ingestion.ingest_session import NAME_TO_CODE, ingest_session

log = structlog.get_logger()

# Only start ingesting a session this many hours after it started. Keeps us from
# grabbing a session that is still running (or whose data is still settling).
COMPLETION_BUFFER_HOURS = 6


def _event_sessions(event) -> list[tuple[str, object]]:
    """Return [(fastf1_session_name, session_date), ...] for an event row."""
    sessions: list[tuple[str, object]] = []
    for i in range(1, 6):
        name = event.get(f"Session{i}")
        if name is None or not str(name).strip() or str(name) == "nan":
            continue
        date = event.get(f"Session{i}DateUtc")
        sessions.append((str(name), date))
    return sessions


def _session_completed(year: int, session_date, now: datetime) -> bool:
    """Past seasons are always done; the current season needs the buffer."""
    if year < now.year:
        return True
    if session_date is None:
        return False
    try:
        if getattr(session_date, "tzinfo", None) is None:
            session_date = session_date.replace(tzinfo=timezone.utc)
        hours_since = (now - session_date).total_seconds() / 3600
        return hours_since > COMPLETION_BUFFER_HOURS
    except Exception:
        return year < now.year


def run_year(
    year: int, skip_telemetry: bool = False, dry_run: bool = False
) -> tuple[int, int]:
    """Ingest every missing completed session for a single year.

    Returns (new_sessions, failed).
    """
    import fastf1  # heavy — lazy

    now = datetime.now(timezone.utc)
    engine = create_engine(settings.db_url)
    try:
        ingested = get_ingested_sessions(engine)

        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
        except Exception as e:
            log.error("backfill.schedule_failed", year=year, error=str(e))
            return 0, 0

        new_sessions = 0
        failed = 0
        skipped = 0

        for _, event in schedule.iterrows():
            if str(event.get("EventFormat", "")).lower() == "testing":
                continue
            gp_name = str(event["EventName"])
            gp_short = gp_name.replace(" Grand Prix", "").replace(" ePrix", "")

            for session_name, session_date in _event_sessions(event):
                code = NAME_TO_CODE.get(session_name)
                if not code:
                    log.warning(
                        "backfill.unknown_session",
                        year=year,
                        gp=gp_name,
                        session=session_name,
                    )
                    continue

                key = (year, gp_name, code)
                if key in ingested:
                    skipped += 1
                    continue

                if not _session_completed(year, session_date, now):
                    log.info(
                        "backfill.not_ready",
                        year=year,
                        gp=gp_short,
                        session=code,
                    )
                    continue

                if dry_run:
                    log.info(
                        "backfill.would_ingest",
                        year=year,
                        gp=gp_short,
                        session=code,
                    )
                    new_sessions += 1
                    ingested.add(key)
                    continue

                try:
                    session_key = ingest_session(
                        year, gp_short, session_name, skip_telemetry=skip_telemetry
                    )
                except Exception as e:
                    if (
                        type(e).__name__ == "DataNotLoadedError"
                        or "DataNotLoadedError" in str(type(e))
                        or "not been loaded yet" in str(e).lower()
                    ):
                        log.warning(
                            "backfill.not_ready",
                            year=year,
                            gp=gp_short,
                            session=code,
                            reason="Data not yet available upstream",
                        )
                        session_key = None
                    else:
                        raise

                if session_key is not None:
                    new_sessions += 1
                    ingested.add(key)
                else:
                    failed += 1

        log.info(
            "backfill.year_done",
            year=year,
            new_sessions=new_sessions,
            failed=failed,
            already_in_db=skipped,
        )
        return new_sessions, failed
    finally:
        engine.dispose()


def run(
    start_year: int, end_year: int, skip_telemetry: bool = False, dry_run: bool = False
) -> int:
    total_new = 0
    total_failed = 0
    for year in range(start_year, end_year + 1):
        new, failed = run_year(year, skip_telemetry=skip_telemetry, dry_run=dry_run)
        total_new += new
        total_failed += failed

    log.info(
        "backfill.done",
        start_year=start_year,
        end_year=end_year,
        new_sessions=total_new,
        failed=total_failed,
    )

    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as output:
            output.write(f"new_sessions={total_new}\n")
            output.write(f"failed={total_failed}\n")

    return total_failed


def main():
    parser = argparse.ArgumentParser(description="Backfill historical F1 sessions")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--skip-telemetry", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List sessions that would be ingested without writing anything",
    )
    args = parser.parse_args()

    if args.end_year < args.start_year:
        parser.error("--end-year must be >= --start-year")

    failed = run(
        args.start_year,
        args.end_year,
        skip_telemetry=args.skip_telemetry,
        dry_run=args.dry_run,
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
