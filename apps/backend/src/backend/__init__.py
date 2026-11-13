import re

import structlog
from flask import Flask, request
from flask_compress import Compress
from flask_cors import CORS
from sqlalchemy import create_engine

from backend import auth, extensions
from backend.config import settings

_SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._~+/=-]+)")


def _redact(_logger, _method, event_dict):
    """Keep API keys and bearer tokens out of log lines."""
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = _SECRET.sub("[redacted]", value)
    return event_dict


structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact,
        structlog.dev.ConsoleRenderer(),
    ]
)

log = structlog.get_logger()

# BoxUp keeps race data public. Only these API areas need a Clerk login:
# race predictions and the (optional) AI agent / analyst endpoints.
_PROTECTED_PATTERN = re.compile(
    r"^/api/v1/(?:sessions/\d+/predictions|predictions(?:/|$)|agent(?:/|$))"
)

# Per-login responses for finished sessions change rarely; let the browser reuse them.
_CACHEABLE_PARTS = (
    "/analysis/",
    "/telemetry",
    "/laps",
    "/fastest",
    "/strategy",
    "/race-order",
    "/drivers",
)


def create_app() -> Flask:
    app = Flask(__name__)

    app.config["SECRET_KEY"] = settings.secret_key
    app.config["DEBUG"] = settings.debug
    app.config["TESTING"] = settings.testing

    cors_origins = [o.strip().rstrip("/") for o in settings.cors_origins.split(",") if o.strip()]
    if settings.cors_origin_regex:
        # e.g. Vercel preview deployments: ^https://formula-1-[a-z0-9-]+\.vercel\.app$
        cors_origins.append(settings.cors_origin_regex)
    CORS(app, origins=cors_origins, max_age=600)
    Compress(app)

    extensions.engine = create_engine(
        settings.db_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
    )

    from backend.api.v1.sessions import sessions_bp
    from backend.api.v1.laps import laps_bp
    from backend.api.v1.drivers import drivers_bp
    from backend.api.v1.driver_profile import driver_profile_bp
    from backend.api.v1.telemetry import telemetry_bp
    from backend.api.v1.strategy import strategy_bp
    from backend.api.v1.analysis import analysis_bp
    from backend.api.v1.predictions import predictions_bp
    from backend.api.v1.schedule import schedule_bp
    from backend.api.v1.stats import stats_bp
    from backend.health import health_bp
    from backend.api.v1.agent import agent_bp
    from backend.api.v1.analyst import analyst_bp
    from backend.api.v1.driver_images import driver_images_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(sessions_bp, url_prefix="/api/v1")
    app.register_blueprint(laps_bp, url_prefix="/api/v1")
    app.register_blueprint(drivers_bp, url_prefix="/api/v1")
    app.register_blueprint(driver_profile_bp, url_prefix="/api/v1")
    app.register_blueprint(telemetry_bp, url_prefix="/api/v1")
    app.register_blueprint(strategy_bp, url_prefix="/api/v1")
    app.register_blueprint(analysis_bp, url_prefix="/api/v1")
    app.register_blueprint(predictions_bp, url_prefix="/api/v1")
    app.register_blueprint(schedule_bp, url_prefix="/api/v1")
    app.register_blueprint(stats_bp, url_prefix="/api/v1")
    app.register_blueprint(agent_bp, url_prefix="/api/v1")
    app.register_blueprint(analyst_bp, url_prefix="/api/v1")
    app.register_blueprint(driver_images_bp, url_prefix="/api/v1")

    @app.before_request
    def require_login_for_api():
        if not _PROTECTED_PATTERN.match(request.path):
            return None
        return auth.require_api_auth()

    @app.after_request
    def add_cache_headers(resp):
        if (
            request.method == "GET"
            and resp.status_code == 200
            and request.path.startswith("/api/v1/sessions/")
            and any(part in request.path for part in _CACHEABLE_PARTS)
        ):
            resp.headers.setdefault(
                "Cache-Control", "private, max-age=60, stale-while-revalidate=300"
            )
        return resp

    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Not found", "code": 404}, 404

    @app.errorhandler(500)
    def server_error(e):
        log.exception("unhandled_exception", error=str(e))
        return {"error": "Internal server error", "code": 500}, 500

    log.info("app.created", debug=settings.debug or app.debug)
    return app
