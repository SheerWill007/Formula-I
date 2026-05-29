"""Celery task: compute telemetry stats after ingestion."""
from workers.celery_app import app
import structlog

log = structlog.get_logger()


@app.task(name='workers.tasks.stats.compute_stats')
def compute_stats(session_key: int):
    from ml.telemetry_stats import compute_stats_for_session
    count = compute_stats_for_session(session_key)
    log.info("task.stats.done", session_key=session_key, rows=count)
    return {"session_key": session_key, "rows": count}
