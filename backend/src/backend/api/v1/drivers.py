"""
Drivers API endpoints.

GET /api/v1/sessions/<key>/drivers                → all drivers
GET /api/v1/sessions/<key>/drivers/<num>/compare  → head-to-head stats
"""
from flask import Blueprint, jsonify
from sqlalchemy import text

from backend.extensions import engine

drivers_bp = Blueprint("drivers", __name__)


@drivers_bp.get("/sessions/<int:session_key>/drivers")
def list_drivers(session_key: int):
    """All drivers in a session with their best lap time."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                d.driver_number,
                d.full_name,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                MIN(l.lap_time_ms) AS best_lap_ms,
                COUNT(l.lap_number) AS total_laps
            FROM drivers d
            LEFT JOIN lap_times l
                ON l.driver_number = d.driver_number
                AND l.session_key  = d.session_key
                AND l.deleted      = FALSE
            WHERE d.session_key = :key
            GROUP BY
                d.driver_number, d.full_name, d.abbreviation,
                d.team_name, d.team_colour
            ORDER BY best_lap_ms ASC NULLS LAST
        """), {"key": session_key}).mappings().all()

    return jsonify([dict(r) for r in rows])


@drivers_bp.get("/sessions/<int:session_key>/drivers/compare")
def compare_drivers(session_key: int):
    """
    Compare multiple drivers side by side.
    Query param: ?drivers=44,63,4  (comma-separated driver numbers)

    Returns best lap, sector bests, theoretical best, and
    sector-by-sector delta vs the fastest driver.
    """
    from flask import request
    drivers_param = request.args.get("drivers", "")

    if not drivers_param:
        return {"error": "Provide ?drivers=44,63,4"}, 400

    try:
        driver_nums = [int(d.strip()) for d in drivers_param.split(",")]
    except ValueError:
        return {"error": "Driver numbers must be integers"}, 400

    if len(driver_nums) < 2:
        return {"error": "Provide at least 2 driver numbers"}, 400

    results = []

    with engine.connect() as conn:
        for num in driver_nums:
            stats = conn.execute(text("""
                SELECT
                    d.driver_number,
                    d.abbreviation,
                    d.team_name,
                    d.team_colour,
                    MIN(l.lap_time_ms)                           AS best_lap_ms,
                    MIN(l.s1_ms)                                 AS best_s1_ms,
                    MIN(l.s2_ms)                                 AS best_s2_ms,
                    MIN(l.s3_ms)                                 AS best_s3_ms,
                    MIN(l.s1_ms) + MIN(l.s2_ms) + MIN(l.s3_ms) AS theoretical_best_ms,
                    STDDEV(l.lap_time_ms)                        AS lap_time_stddev,
                    COUNT(l.lap_number)                          AS total_laps
                FROM drivers d
                JOIN lap_times l
                    ON l.driver_number = d.driver_number
                    AND l.session_key  = d.session_key
                WHERE d.session_key   = :session_key
                  AND d.driver_number = :driver_number
                  AND l.lap_time_ms   IS NOT NULL
                  AND l.deleted       = FALSE
                GROUP BY d.driver_number, d.abbreviation, d.team_name, d.team_colour
            """), {"session_key": session_key, "driver_number": num}
            ).mappings().first()

            if stats:
                results.append(dict(stats))

    if not results:
        return {"error": "No data found for given drivers"}, 404

    best_lap = min(float(r["best_lap_ms"]) for r in results if r["best_lap_ms"])
    for r in results:
        if r["best_lap_ms"]:
            r["gap_to_fastest_ms"] = round(float(r["best_lap_ms"]) - best_lap, 3)
            r["theoretical_best_ms"] = float(r["theoretical_best_ms"]) if r.get("theoretical_best_ms") else None
        else:
            r["gap_to_fastest_ms"] = None


    return jsonify(results)
