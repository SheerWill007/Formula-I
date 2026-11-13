"""
stats.py: /api/v1/stats

Public, aggregate-only platform counters for the marketing landing page.
No per-user or per-session detail is exposed, so no auth is required.
"""

from __future__ import annotations

import logging
import time

from flask import Blueprint, jsonify
from sqlalchemy import text

from backend import extensions

log = logging.getLogger(__name__)

stats_bp = Blueprint("stats", __name__)

_TTL_SECONDS = 300
_cache: dict = {"at": 0.0, "body": None}


@stats_bp.get("/stats")
def platform_stats():
    now = time.monotonic()
    if _cache["body"] is not None and now - _cache["at"] < _TTL_SECONDS:
        return jsonify(_cache["body"])

    try:
        with extensions.engine.connect() as conn:
            sessions = conn.execute(
                text(
                    "SELECT COUNT(*) AS sessions, "
                    "COUNT(DISTINCT year) AS seasons, "
                    "MIN(year) AS first_season, MAX(year) AS last_season "
                    "FROM sessions"
                )
            ).mappings().one()
            laps = conn.execute(text("SELECT COUNT(*) AS laps FROM lap_times")).scalar()
    except Exception as exc:
        log.warning("stats query failed: %s", exc)
        return jsonify({"error": "Stats unavailable"}), 503

    body = {
        "sessions": int(sessions["sessions"] or 0),
        "seasons": int(sessions["seasons"] or 0),
        "first_season": sessions["first_season"],
        "last_season": sessions["last_season"],
        "laps": int(laps or 0),
    }
    _cache.update(at=now, body=body)
    return jsonify(body)
