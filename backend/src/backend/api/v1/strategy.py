"""
Strategy API — tyre stints per driver for race sessions.
"""
from flask import Blueprint, jsonify
from sqlalchemy import text
from backend.extensions import get_engine

strategy_bp = Blueprint("strategy", __name__)

# Fallback colours if team_colour is null in DB
TEAM_COLOURS = {
    'McLaren': 'FF8000', 'Ferrari': 'E8002D', 'Red Bull Racing': '3671C6',
    'Mercedes': '27F4D2', 'Aston Martin': '229971', 'Alpine': 'FF87BC',
    'Williams': '64C4FF', 'Haas F1 Team': 'B6BABD', 'Haas': 'B6BABD',
    'Kick Sauber': '52E252', 'Sauber': '52E252', 'RB': '6692FF',
    'Racing Bulls': '6692FF', 'Cadillac': 'C8A217', 'Audi': 'C8A217',
}


def _resolve(colour, team_name):
    if colour and colour.strip():
        return colour.lstrip('#')
    for k, v in TEAM_COLOURS.items():
        if team_name and (k in team_name or team_name in k):
            return v
    return '666666'


@strategy_bp.get("/sessions/<int:session_key>/strategy")
def race_strategy(session_key: int):
    engine = get_engine()
    with engine.connect() as conn:
        has_stints = conn.execute(text("""
            SELECT COUNT(*) FROM lap_times
            WHERE session_key = :sk AND stint IS NOT NULL
        """), {"sk": session_key}).scalar()

        if has_stints:
            rows = conn.execute(text("""
                SELECT
                    l.driver_number,
                    d.abbreviation,
                    d.team_name,
                    d.team_colour,
                    MIN(l.position) FILTER (WHERE l.position IS NOT NULL) AS grid_pos,
                    l.stint,
                    l.compound,
                    l.fresh_tyre,
                    MIN(l.lap_number) AS start_lap,
                    MAX(l.lap_number) AS end_lap,
                    COUNT(*)          AS laps
                FROM lap_times l
                JOIN drivers d
                    ON d.driver_number = l.driver_number
                    AND d.session_key  = l.session_key
                WHERE l.session_key = :sk
                  AND l.compound    IS NOT NULL
                  AND l.deleted     = FALSE
                GROUP BY
                    l.driver_number, d.abbreviation, d.team_name,
                    d.team_colour, l.stint, l.compound, l.fresh_tyre
                ORDER BY
                    MIN(l.position) ASC NULLS LAST,
                    l.driver_number,
                    l.stint ASC NULLS LAST
            """), {"sk": session_key}).mappings().all()
        else:
            rows = conn.execute(text("""
                WITH stint_calc AS (
                    SELECT driver_number, lap_number, compound, fresh_tyre,
                        SUM(CASE WHEN compound != LAG(compound) OVER w
                                    OR LAG(compound) OVER w IS NULL
                             THEN 1 ELSE 0 END) OVER w AS stint
                    FROM lap_times
                    WHERE session_key = :sk AND compound IS NOT NULL AND deleted = FALSE
                    WINDOW w AS (PARTITION BY driver_number ORDER BY lap_number)
                )
                SELECT
                    sc.driver_number, d.abbreviation, d.team_name, d.team_colour,
                    sc.stint, sc.compound, sc.fresh_tyre,
                    MIN(sc.lap_number) AS start_lap,
                    MAX(sc.lap_number) AS end_lap,
                    COUNT(*) AS laps
                FROM stint_calc sc
                JOIN drivers d ON d.driver_number = sc.driver_number AND d.session_key = :sk
                GROUP BY sc.driver_number, d.abbreviation, d.team_name, d.team_colour,
                         sc.stint, sc.compound, sc.fresh_tyre
                ORDER BY sc.driver_number, sc.stint
            """), {"sk": session_key}).mappings().all()

        if not rows:
            return jsonify({"total_laps": 0, "stints": []})

        total_laps = conn.execute(text("""
            SELECT MAX(lap_number) FROM lap_times WHERE session_key = :sk
        """), {"sk": session_key}).scalar() or 0

    stints = []
    for r in rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        stints.append(d)

    return jsonify({"total_laps": total_laps, "stints": stints})


@strategy_bp.get("/sessions/<int:session_key>/race-order")
def race_order(session_key: int):
    """Return the race finishing order for a race session."""
    engine = get_engine()
    with engine.connect() as conn:
        # Check if session exists and is a race
        session = conn.execute(text("""
            SELECT session_type, gp_name, year
            FROM sessions WHERE session_key = :sk
        """), {"sk": session_key}).mappings().first()

        if not session:
            return jsonify({"error": "Session not found"}), 404

        # Get finishing positions from lap_times (final position of each driver)
        rows = conn.execute(text("""
            SELECT
                d.driver_number,
                d.abbreviation,
                d.full_name,
                d.team_name,
                d.team_colour,
                MAX(l.position) AS finishing_position,
                MAX(l.lap_number) AS laps_completed,
                MIN(l.lap_time_ms) AS best_lap_ms
            FROM drivers d
            LEFT JOIN lap_times l
                ON l.driver_number = d.driver_number
                AND l.session_key  = d.session_key
                AND l.deleted      = FALSE
            WHERE d.session_key = :sk
            GROUP BY d.driver_number, d.abbreviation, d.full_name, d.team_name, d.team_colour
            ORDER BY finishing_position ASC NULLS LAST, d.driver_number ASC
        """), {"sk": session_key}).mappings().all()

        if not rows:
            return jsonify({"error": "No race data found"}), 404

    positions = []
    for r in rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        positions.append(d)

    return jsonify({"finishing_order": positions})
