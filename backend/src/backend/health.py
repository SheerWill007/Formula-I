"""
Health check endpoint.

GET /health → {"status": "ok", "database": "ok", "version": "0.1.0"}

Used by Docker, load balancers, and monitoring tools to check if
the service is alive and its dependencies are reachable.
"""
from flask import Blueprint, jsonify
from sqlalchemy import text

from backend.extensions import engine

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    # Check database connectivity
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"

    status = "ok" if db_status == "ok" else "degraded"
    code   = 200  if db_status == "ok" else 503

    return jsonify({
        "status":   status,
        "database": db_status,
        "version":  "0.1.0",
    }), code
