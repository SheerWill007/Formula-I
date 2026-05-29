"""Celery task: retrain ML model after new race data is ingested."""
from workers.celery_app import app
import structlog

log = structlog.get_logger()


@app.task(name='workers.tasks.train.retrain_model')
def retrain_model():
    """
    Retrain the FLAML race prediction model on all available data.
    Triggered automatically after a new race weekend is ingested.
    """
    import subprocess
    import sys

    log.info("task.train.start")
    result = subprocess.run(
        [sys.executable, '-m', 'ml.train'],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        log.error("task.train.failed", stderr=result.stderr)
        return {"success": False, "error": result.stderr}

    log.info("task.train.done", stdout=result.stdout[-500:])
    return {"success": True}
