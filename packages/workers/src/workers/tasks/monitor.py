"""
Celery task: monitor for new completed F1 sessions.

Runs on schedule (Sunday 20:00 UTC + Monday 08:00 UTC).
Checks the current-season calendar against what's in the DB and
triggers ingestion for any missing sessions.
"""
from __future__ import annotations
import datetime
import structlog
from sqlalchemy import create_engine, text
from workers.celery_app import app
from workers.config import settings

log = structlog.get_logger()

SPRINT_GPS = {
    'Chinese Grand Prix',
    'Miami Grand Prix',
    'Canadian Grand Prix',
    'British Grand Prix',
    'Dutch Grand Prix',
    'Singapore Grand Prix',
}


def get_engine():
    return create_engine(settings.database_url)


@app.task(name='workers.tasks.monitor.check_completed_sessions')
def check_completed_sessions():
    """
    Check the current calendar for race weekends that have completed
    but haven't been ingested yet. Triggers ingest_weekend for each.

    Logic:
    1. Fetch the current-year schedule from FastF1
    2. Filter to weekends that ended more than 4 hours ago
       (FastF1 data takes ~2-4h to appear after race end)
    3. Check DB for existing sessions
    4. Trigger ingestion for any missing weekends
    """
    import fastf1
    current_year = datetime.datetime.now(datetime.timezone.utc).year

    log.info("monitor.check.start")

    try:
        schedule = fastf1.get_event_schedule(current_year, include_testing=False)
    except Exception as e:
        log.error("monitor.schedule_fetch_failed", error=str(e))
        return {"error": str(e)}

    now = datetime.datetime.now(datetime.timezone.utc)
    engine = get_engine()
    triggered = []
    skipped   = []

    with engine.connect() as conn:
        for _, event in schedule.iterrows():
            event_date = event['EventDate']
            gp_name    = event['EventName']

            # Convert to UTC-aware datetime (race typically ends ~15:00 local)
            # Add 1 day as conservative estimate for when data is available
            if hasattr(event_date, 'tzinfo') and event_date.tzinfo is None:
                event_date = event_date.replace(tzinfo=datetime.timezone.utc)

            data_available_after = event_date + datetime.timedelta(days=1)

            if now < data_available_after:
                skipped.append(gp_name)
                continue

            # Check if we already have both Q and R for this GP
            existing = conn.execute(text("""
                SELECT session_type FROM sessions
                WHERE year = :year AND gp_name = :gp_name
            """), {"year": current_year, "gp_name": gp_name}).scalars().all()

            required_sessions = {'Q', 'R'}
            if gp_name not in SPRINT_GPS:
                required_sessions.update({'FP1', 'FP2', 'FP3'})
            else:
                required_sessions.add('FP1')

            if required_sessions.issubset(set(existing)):
                log.debug("monitor.already_ingested", gp=gp_name)
                continue

            # Trigger ingestion
            is_sprint = gp_name in SPRINT_GPS
            log.info("monitor.triggering_ingest",
                     gp=gp_name, sprint=is_sprint,
                     existing_sessions=existing, required_sessions=sorted(required_sessions))

            from workers.tasks.ingest import ingest_weekend
            ingest_weekend.delay(current_year, _gp_to_fastf1_name(gp_name), is_sprint)
            triggered.append(gp_name)

    log.info("monitor.check.done",
             triggered=triggered,
             skipped_future=len(skipped))

    return {"triggered": triggered, "skipped_future": len(skipped)}


def _gp_to_fastf1_name(gp_name: str) -> str:
    """
    Convert full GP name to FastF1 short name.
    FastF1 accepts partial matches so we extract the key word.

    'Australian Grand Prix' → 'Australian'
    'São Paulo Grand Prix'  → 'São Paulo'
    """
    return gp_name.replace(' Grand Prix', '').strip()
