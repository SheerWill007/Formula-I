"""
Data retention policy.

Raw telemetry: kept 7 days (TimescaleDB retention policy handles this automatically)
lap_telemetry_stats: kept forever (pre-computed, small)
lap_times: kept forever
ML predictions: kept forever

This task is a manual override for immediate purges and reporting.
"""
from __future__ import annotations
from workers.celery_app import app
from workers.config import settings
import structlog

log = structlog.get_logger()


def get_engine():
    from sqlalchemy import create_engine
    return create_engine(settings.database_url)


@app.task(name='workers.tasks.retention.purge_telemetry')
def purge_telemetry(days: int = 7):
    """
    Manually purge telemetry older than `days` days.
    TimescaleDB retention policy runs this automatically,
    but this task allows manual triggering and reporting.
    """
    from sqlalchemy import text
    engine = get_engine()

    with engine.connect() as conn:
        # Count before delete
        before = conn.execute(text(
            "SELECT COUNT(*) FROM telemetry"
        )).scalar()

        # Delete rows older than cutoff
        deleted = conn.execute(text(f"""
            DELETE FROM telemetry
            WHERE recorded_at < NOW() - INTERVAL '{days} days'
        """)).rowcount

        conn.commit()

        after = conn.execute(text(
            "SELECT COUNT(*) FROM telemetry"
        )).scalar()

    log.info("retention.purged",
             deleted=deleted,
             before=before,
             after=after,
             days=days)

    return {
        "deleted":  deleted,
        "before":   before,
        "after":    after,
        "days":     days,
    }


@app.task(name='workers.tasks.retention.storage_report')
def storage_report():
    """Report current storage usage per table."""
    from sqlalchemy import text
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
                pg_total_relation_size(relid) AS size_bytes
            FROM pg_catalog.pg_statio_user_tables
            ORDER BY pg_total_relation_size(relid) DESC
        """)).mappings().all()

    report = [dict(r) for r in rows]
    for r in report:
        log.info("storage.table",
                 table=r['table_name'],
                 size=r['total_size'])

    return report


@app.task(name='workers.tasks.retention.purge_practice_sessions')
def purge_practice_sessions(current_year: int, current_gp: str):
    """
    Keep only the practice sessions needed for the active modelling window.

    Policy:
    - Keep FP1/FP2/FP3 for the current GP in the current season
    - Keep FP1/FP2/FP3 for the same GP from the previous season
    - Purge all other practice sessions to stay within Railway storage limits
    """
    from sqlalchemy import text

    engine = get_engine()
    practice_types = ('FP1', 'FP2', 'FP3')

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT session_key
            FROM sessions
            WHERE session_type = ANY(:practice_types)
              AND NOT (
                (year = :current_year AND gp_name = :current_gp)
                OR
                (year = :previous_year AND gp_name = :current_gp)
              )
        """), {
            "practice_types": list(practice_types),
            "current_year": current_year,
            "previous_year": current_year - 1,
            "current_gp": current_gp,
        }).scalars().all()

        session_keys = list(rows)
        if not session_keys:
          log.info("retention.practice_purge_skipped", year=current_year, gp=current_gp, deleted_sessions=0)
          return {"deleted_sessions": 0}

        conn.execute(text("DELETE FROM telemetry WHERE session_key = ANY(:session_keys)"), {"session_keys": session_keys})
        conn.execute(text("DELETE FROM lap_telemetry_stats WHERE session_key = ANY(:session_keys)"), {"session_keys": session_keys})
        conn.execute(text("DELETE FROM lap_times WHERE session_key = ANY(:session_keys)"), {"session_keys": session_keys})
        conn.execute(text("DELETE FROM drivers WHERE session_key = ANY(:session_keys)"), {"session_keys": session_keys})
        conn.execute(text("DELETE FROM sessions WHERE session_key = ANY(:session_keys)"), {"session_keys": session_keys})
        conn.commit()

    log.info(
        "retention.practice_purged",
        year=current_year,
        gp=current_gp,
        deleted_sessions=len(session_keys),
    )
    return {"deleted_sessions": len(session_keys)}
