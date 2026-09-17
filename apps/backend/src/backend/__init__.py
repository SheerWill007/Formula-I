import structlog
import threading
import time
from flask import Flask
from flask_cors import CORS
from sqlalchemy import create_engine

from backend import extensions
from backend.config import settings

log = structlog.get_logger()
_auto_ingest_thread: threading.Thread | None = None


def _start_auto_ingest_scheduler() -> None:
    global _auto_ingest_thread

    if _auto_ingest_thread and _auto_ingest_thread.is_alive():
        return

    interval_seconds = max(settings.auto_ingest_interval_minutes, 15) * 60

    def runner() -> None:
        from ingestion.auto_ingest import run_once

        if settings.auto_ingest_on_startup:
            try:
                run_once()
            except Exception as exc:
                log.warning("auto_ingest.startup_failed", error=str(exc))

        while True:
            time.sleep(interval_seconds)
            try:
                run_once()
            except Exception as exc:
                log.warning("auto_ingest.interval_failed", error=str(exc))

    _auto_ingest_thread = threading.Thread(
        target=runner,
        name="pitwall-auto-ingest",
        daemon=True,
    )
    _auto_ingest_thread.start()
    log.info(
        "auto_ingest.scheduler_started",
        interval_minutes=max(settings.auto_ingest_interval_minutes, 15),
        run_on_startup=settings.auto_ingest_on_startup,
    )


def create_app() -> Flask:
    app = Flask(__name__)

    app.config["SECRET_KEY"] = settings.secret_key
    app.config["DEBUG"] = settings.debug
    app.config["TESTING"] = settings.testing

    # Allow Next.js dev server to call the API
    CORS(app, origins="*")

    extensions.engine = create_engine(
        settings.db_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

    from backend.api.v1.sessions import sessions_bp
    from backend.api.v1.laps import laps_bp
    from backend.api.v1.drivers import drivers_bp
    from backend.api.v1.telemetry import telemetry_bp
    from backend.api.v1.strategy import strategy_bp
    from backend.api.v1.analysis import analysis_bp
    from backend.api.v1.predictions import predictions_bp
    from backend.api.v1.schedule import schedule_bp
    from backend.health import health_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(sessions_bp, url_prefix="/api/v1")
    app.register_blueprint(laps_bp, url_prefix="/api/v1")
    app.register_blueprint(drivers_bp, url_prefix="/api/v1")
    app.register_blueprint(telemetry_bp, url_prefix="/api/v1")
    app.register_blueprint(strategy_bp, url_prefix="/api/v1")
    app.register_blueprint(analysis_bp, url_prefix="/api/v1")
    app.register_blueprint(predictions_bp, url_prefix="/api/v1")
    app.register_blueprint(schedule_bp, url_prefix="/api/v1")

    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Not found", "code": 404}, 404

    @app.errorhandler(500)
    def server_error(e):
        log.exception("unhandled_exception", error=str(e))
        return {"error": "Internal server error", "code": 500}, 500

    if settings.auto_ingest_enabled and not settings.testing and not settings.debug and not app.debug:
        _start_auto_ingest_scheduler()

    log.info("app.created", debug=settings.debug or app.debug)
    return app
