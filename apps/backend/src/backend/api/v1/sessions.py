from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from backend import extensions

sessions_bp = Blueprint("sessions", __name__)


def _is_missing_table_error(exc: ProgrammingError) -> bool:
    return "UndefinedTable" in exc.__class__.__name__ or "does not exist" in str(exc.orig)


def _missing_schema_response():
    return jsonify({
        "error": "Database schema is not initialized",
        "detail": "The backend connected to Postgres, but required Pitwall tables such as sessions do not exist.",
        "suggested_command": "uv run alembic -c apps/backend/alembic.ini upgrade head",
    }), 503


@sessions_bp.get("/sessions")
def list_sessions():
    """
    List all sessions ordered by date descending.
    Qualifying sessions appear before Race sessions on the same date
    so the home page hero shows the most recent qualifying.
    """
    try:
        with extensions.engine.connect() as conn:
            rows = (
                conn.execute(
                    text("""
            SELECT
                session_key, year, gp_name, country,
                session_type, session_name,
                date_start, date_end,
                track_temp_c, air_temp_c, humidity_pct,
                rainfall, wind_speed_ms
            FROM sessions
            ORDER BY
                date_start DESC NULLS LAST,
                -- Within same date: Q before R so home hero shows qualifying
                CASE session_type
                    WHEN 'Q'  THEN 1
                    WHEN 'SQ' THEN 2
                    WHEN 'S'  THEN 3
                    WHEN 'R'  THEN 4
                    ELSE 5
                END ASC
        """)
                )
                .mappings()
                .all()
            )
    except ProgrammingError as exc:
        if _is_missing_table_error(exc):
            return _missing_schema_response()
        raise
    return jsonify([dict(r) for r in rows])


@sessions_bp.get("/sessions/<int:session_key>")
def get_session(session_key: int):
    with extensions.engine.connect() as conn:
        row = (
            conn.execute(
                text("""
            SELECT
                session_key, year, gp_name, country,
                session_type, session_name,
                date_start, date_end,
                track_temp_c, air_temp_c, humidity_pct,
                rainfall, wind_speed_ms
            FROM sessions
            WHERE session_key = :sk
        """),
                {"sk": session_key},
            )
            .mappings()
            .first()
        )

        if not row:
            return {"error": "Session not found"}, 404

        result = dict(row)

        # Include drivers for this session
        drivers = (
            conn.execute(
                text("""
            SELECT
                driver_number, full_name, abbreviation,
                team_name, team_colour
            FROM drivers
            WHERE session_key = :sk
            ORDER BY driver_number
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )
        result["drivers"] = [dict(d) for d in drivers]

    return jsonify(result)


@sessions_bp.get("/sessions/<int:session_key>/race-results")
def race_results(session_key: int):
    """
    Race finishing order.

    Uses the `position` column (FastF1 live position per lap) —
    takes each driver's position on their final lap as finishing position.
    Falls back to total laps completed + cumulative time if position is null.
    """
    with extensions.engine.connect() as conn:
        # Check if position data exists
        has_position = conn.execute(
            text("""
            SELECT COUNT(*) FROM lap_times
            WHERE session_key = :sk AND position IS NOT NULL
        """),
            {"sk": session_key},
        ).scalar()

        if has_position:
            # Use position on the final lap for each driver
            rows = (
                conn.execute(
                    text("""
                WITH final_lap AS (
                    SELECT DISTINCT ON (l.driver_number)
                        l.driver_number,
                        l.lap_number   AS total_laps,
                        l.position     AS finish_pos,
                        l.compound,
                        l.lap_time_ms  AS last_lap_ms
                    FROM lap_times l
                    WHERE l.session_key = :sk
                    ORDER BY l.driver_number, l.lap_number DESC
                ),
                best_lap AS (
                    SELECT driver_number, MIN(lap_time_ms) AS best_lap_ms
                    FROM lap_times
                    WHERE session_key = :sk AND lap_time_ms IS NOT NULL
                    GROUP BY driver_number
                )
                SELECT
                    fl.driver_number,
                    d.full_name,
                    d.abbreviation,
                    d.team_name,
                    d.team_colour,
                    fl.total_laps,
                    fl.finish_pos,
                    fl.compound,
                    bl.best_lap_ms
                FROM final_lap fl
                JOIN drivers d ON d.driver_number = fl.driver_number AND d.session_key = :sk
                JOIN best_lap bl ON bl.driver_number = fl.driver_number
                ORDER BY fl.finish_pos ASC NULLS LAST, fl.total_laps DESC
            """),
                    {"sk": session_key},
                )
                .mappings()
                .all()
            )
        else:
            # Fallback: order by total laps then cumulative time
            rows = (
                conn.execute(
                    text("""
                WITH last_lap AS (
                    SELECT DISTINCT ON (l.driver_number)
                        l.driver_number,
                        l.lap_number AS total_laps,
                        l.compound,
                        l.recorded_at AS finished_at
                    FROM lap_times l
                    WHERE l.session_key = :sk
                    ORDER BY l.driver_number, l.lap_number DESC
                ),
                race_time AS (
                    SELECT driver_number, SUM(lap_time_ms) AS total_ms
                    FROM lap_times
                    WHERE session_key = :sk AND lap_time_ms IS NOT NULL AND deleted = FALSE
                    GROUP BY driver_number
                ),
                best_lap AS (
                    SELECT driver_number, MIN(lap_time_ms) AS best_lap_ms
                    FROM lap_times
                    WHERE session_key = :sk AND lap_time_ms IS NOT NULL
                    GROUP BY driver_number
                )
                SELECT
                    ll.driver_number,
                    d.full_name,
                    d.abbreviation,
                    d.team_name,
                    d.team_colour,
                    ll.total_laps,
                    NULL::int AS finish_pos,
                    ll.compound,
                    bl.best_lap_ms,
                    rt.total_ms
                FROM last_lap ll
                JOIN drivers d ON d.driver_number = ll.driver_number AND d.session_key = :sk
                JOIN best_lap bl ON bl.driver_number = ll.driver_number
                LEFT JOIN race_time rt ON rt.driver_number = ll.driver_number
                ORDER BY ll.total_laps DESC, rt.total_ms ASC NULLS LAST
            """),
                    {"sk": session_key},
                )
                .mappings()
                .all()
            )

        if not rows:
            return jsonify([])

        results = [dict(r) for r in rows]

        # Resolve team colours
        from backend.api.v1.strategy import _resolve

        for r in results:
            r["team_colour"] = _resolve(r.get("team_colour"), r.get("team_name"))

        # Calculate gaps to winner using cumulative lap time
        sums = (
            conn.execute(
                text("""
            SELECT driver_number, SUM(lap_time_ms) AS total_ms
            FROM lap_times
            WHERE session_key = :sk AND lap_time_ms IS NOT NULL AND deleted = FALSE
            GROUP BY driver_number
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )
        sum_map = {r["driver_number"]: r["total_ms"] for r in sums}

        winner_total = sum_map.get(results[0]["driver_number"])
        max_laps = results[0]["total_laps"]

        for i, r in enumerate(results):
            driver_total = sum_map.get(r["driver_number"])
            if i == 0:
                r["gap_ms"] = None
                r["laps_down"] = 0
            elif r["total_laps"] < max_laps:
                r["gap_ms"] = None
                r["laps_down"] = int(max_laps - r["total_laps"])
            elif driver_total and winner_total:
                r["gap_ms"] = float(driver_total - winner_total)
                r["laps_down"] = 0
            else:
                r["gap_ms"] = None
                r["laps_down"] = 0

    return jsonify(results)


# ── Championship standings via Jolpica-F1 (official data) ────────────────────


@sessions_bp.get("/standings/drivers")
def driver_standings():
    """
    Official driver championship standings via FastF1 → Jolpica-F1 API.
    Uses FastF1's caching so repeat calls are instant.

    Query param: ?year=2026 (default: current year)
    """
    import fastf1
    from fastf1.ergast import Ergast
    import os

    year = request.args.get("year", 2026, type=int)

    cache_dir = os.environ.get("FASTF1_CACHE_DIR", "./fastf1_cache")
    try:
        fastf1.Cache.enable_cache(cache_dir)
    except Exception:
        pass

    try:
        with fastf1.Cache.disabled():
            ergast = Ergast()
            result = ergast.get_driver_standings(season=year, result_type="raw")
        # result is an ErgastRawResponse which behaves like a list of rounds
        if not result:
            return jsonify([])

        latest_round_data = result[-1]  # most recent round's data
        latest_round = latest_round_data.get("DriverStandings", [])
        standings = []
        for entry in latest_round:
            driver = entry.get("Driver", {})
            constructors = entry.get("Constructors", [{}])
            team_name = constructors[0].get("name", "") if constructors else ""
            standings.append(
                {
                    "position": entry.get("position"),
                    "points": entry.get("points"),
                    "wins": entry.get("wins"),
                    "code": driver.get("code"),
                    "full_name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip(),
                    "nationality": driver.get("nationality"),
                    "team_name": team_name,
                }
            )
        return jsonify(
            {
                "year": year,
                "round": latest_round_data.get("round", 0),
                "standings": standings,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sessions_bp.get("/standings/constructors")
def constructor_standings():
    """
    Official constructor championship standings via FastF1 → Jolpica-F1 API.
    Query param: ?year=2026
    """
    import fastf1
    from fastf1.ergast import Ergast
    import os

    year = request.args.get("year", 2026, type=int)

    cache_dir = os.environ.get("FASTF1_CACHE_DIR", "./fastf1_cache")
    try:
        fastf1.Cache.enable_cache(cache_dir)
    except Exception:
        pass

    try:
        with fastf1.Cache.disabled():
            ergast = Ergast()
            result = ergast.get_constructor_standings(season=year, result_type="raw")
        if not result:
            return jsonify([])

        latest_round_data = result[-1]
        latest_round = latest_round_data.get("ConstructorStandings", [])
        standings = []
        for entry in latest_round:
            constructor = entry.get("Constructor", {})
            standings.append(
                {
                    "position": entry.get("position"),
                    "points": entry.get("points"),
                    "wins": entry.get("wins"),
                    "team_name": constructor.get("name"),
                    "nationality": constructor.get("nationality"),
                }
            )
        return jsonify(
            {
                "year": year,
                "round": latest_round_data.get("round", 0),
                "standings": standings,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
