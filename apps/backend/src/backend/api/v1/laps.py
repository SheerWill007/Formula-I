from flask import Blueprint, jsonify, request
from sqlalchemy import text
from backend.extensions import engine

laps_bp = Blueprint("laps", __name__)


@laps_bp.get("/sessions/<int:session_key>/laps")
def list_laps(session_key: int):
    driver = request.args.get("driver", type=int)
    params: dict = {"sk": session_key}
    driver_filter = ""
    if driver:
        driver_filter = "AND lt.driver_number = :driver"
        params["driver"] = driver

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(f"""
            SELECT
                lt.driver_number, d.abbreviation,
                d.team_name, d.team_colour,
                lt.lap_number, lt.lap_time_ms,
                lt.s1_ms, lt.s2_ms, lt.s3_ms,
                lt.compound, lt.tyre_life_laps,
                lt.is_personal_best, lt.track_status, lt.position, lt.deleted
            FROM lap_times lt
            JOIN drivers d
                ON d.driver_number = lt.driver_number
                AND d.session_key  = lt.session_key
            WHERE lt.session_key = :sk
              {driver_filter}
            ORDER BY lt.driver_number, lt.lap_number
        """),
                params,
            )
            .mappings()
            .all()
        )
    return jsonify([dict(r) for r in rows])


@laps_bp.get("/sessions/<int:session_key>/fastest")
def fastest_laps(session_key: int):
    """
    Returns each driver's best lap for the session, ordered by lap time.
    Also returns fastest_s1, fastest_s2, fastest_s3 driver info at the top level.
    """
    with engine.connect() as conn:
        # Best lap per driver
        rows = (
            conn.execute(
                text("""
            SELECT DISTINCT ON (lt.driver_number)
                lt.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                lt.lap_number,
                lt.lap_time_ms,
                lt.s1_ms,
                lt.s2_ms,
                lt.s3_ms,
                lt.compound
            FROM lap_times lt
            JOIN drivers d
                ON d.driver_number = lt.driver_number
                AND d.session_key  = lt.session_key
            WHERE lt.session_key  = :sk
              AND lt.lap_time_ms IS NOT NULL
              AND lt.deleted = false
            ORDER BY lt.driver_number, lt.lap_time_ms ASC
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

        laps = [dict(r) for r in rows]
        laps.sort(key=lambda x: x["lap_time_ms"] or float("inf"))

        # Fastest individual sectors (may be different drivers)
        s1_row = (
            conn.execute(
                text("""
            SELECT lt.driver_number, d.abbreviation, d.team_name, d.team_colour, lt.s1_ms
            FROM lap_times lt
            JOIN drivers d ON d.driver_number = lt.driver_number AND d.session_key = lt.session_key
            WHERE lt.session_key = :sk AND lt.s1_ms IS NOT NULL AND lt.deleted = false
            ORDER BY lt.s1_ms ASC LIMIT 1
        """),
                {"sk": session_key},
            )
            .mappings()
            .first()
        )

        s2_row = (
            conn.execute(
                text("""
            SELECT lt.driver_number, d.abbreviation, d.team_name, d.team_colour, lt.s2_ms
            FROM lap_times lt
            JOIN drivers d ON d.driver_number = lt.driver_number AND d.session_key = lt.session_key
            WHERE lt.session_key = :sk AND lt.s2_ms IS NOT NULL AND lt.deleted = false
            ORDER BY lt.s2_ms ASC LIMIT 1
        """),
                {"sk": session_key},
            )
            .mappings()
            .first()
        )

        s3_row = (
            conn.execute(
                text("""
            SELECT lt.driver_number, d.abbreviation, d.team_name, d.team_colour, lt.s3_ms
            FROM lap_times lt
            JOIN drivers d ON d.driver_number = lt.driver_number AND d.session_key = lt.session_key
            WHERE lt.session_key = :sk AND lt.s3_ms IS NOT NULL AND lt.deleted = false
            ORDER BY lt.s3_ms ASC LIMIT 1
        """),
                {"sk": session_key},
            )
            .mappings()
            .first()
        )

    return jsonify(
        {
            "laps": laps,
            "fastest_s1": dict(s1_row) if s1_row else None,
            "fastest_s2": dict(s2_row) if s2_row else None,
            "fastest_s3": dict(s3_row) if s3_row else None,
        }
    )


@laps_bp.get("/sessions/<int:session_key>/drivers/<int:driver_number>/laps")
def driver_laps(session_key: int, driver_number: int):
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            SELECT
                lt.lap_number, lt.lap_time_ms,
                lt.s1_ms, lt.s2_ms, lt.s3_ms,
                lt.compound, lt.tyre_life_laps,
                lt.is_personal_best, lt.track_status, lt.deleted
            FROM lap_times lt
            WHERE lt.session_key   = :sk
              AND lt.driver_number = :dn
            ORDER BY lt.lap_number
        """),
                {"sk": session_key, "dn": driver_number},
            )
            .mappings()
            .all()
        )

        best = (
            conn.execute(
                text("""
            SELECT
                MIN(lap_time_ms) AS best_lap,
                MIN(s1_ms) AS best_s1,
                MIN(s2_ms) AS best_s2,
                MIN(s3_ms) AS best_s3
            FROM lap_times
            WHERE session_key   = :sk
              AND driver_number = :dn
              AND deleted = false
        """),
                {"sk": session_key, "dn": driver_number},
            )
            .mappings()
            .first()
        )

    tb = dict(best) if best else None
    if tb and tb.get("best_s1") and tb.get("best_s2") and tb.get("best_s3"):
        tb["theoretical_best_ms"] = float(tb["best_s1"]) + float(tb["best_s2"]) + float(tb["best_s3"])

    return jsonify(
        {
            "laps": [dict(r) for r in rows],
            "theoretical_best": tb,
        }
    )
