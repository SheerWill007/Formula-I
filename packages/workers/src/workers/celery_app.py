"""
Celery application factory.

Workers handle:
- Session ingestion (triggered manually or by monitor)
- Telemetry stats computation
- ML model retraining
- Data retention (purge old telemetry)

Beat scheduler handles:
- Weekly check for new completed sessions
- Weekly telemetry purge
"""
from celery import Celery
from celery.schedules import crontab
from workers.config import settings

app = Celery(
    'pitwall',
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        'workers.tasks.ingest',
        'workers.tasks.monitor',
        'workers.tasks.stats',
        'workers.tasks.train',
        'workers.tasks.retention',
    ],
)

app.conf.update(
    task_serializer       = 'json',
    result_serializer     = 'json',
    accept_content        = ['json'],
    timezone              = 'UTC',
    enable_utc            = True,
    task_track_started    = True,
    result_expires        = 3600 * 24,  # keep results 24h
    worker_prefetch_multiplier = 1,     # one task at a time (ingestion is heavy)
)

app.conf.beat_schedule = {
    # Check for new sessions every Sunday at 20:00 UTC
    # (safe window — most races finish by 16:00 UTC, FastF1 needs ~3h)
    'check-new-sessions-sunday': {
        'task':     'workers.tasks.monitor.check_completed_sessions',
        'schedule': crontab(hour=20, minute=0, day_of_week=0),
    },
    # Monday 08:00 UTC catchup — in case Sunday missed something
    'check-new-sessions-monday': {
        'task':     'workers.tasks.monitor.check_completed_sessions',
        'schedule': crontab(hour=8, minute=0, day_of_week=1),
    },
    # Weekly telemetry purge — Monday 03:00 UTC
    'purge-old-telemetry': {
        'task':     'workers.tasks.retention.purge_telemetry',
        'schedule': crontab(hour=3, minute=0, day_of_week=1),
    },
}
