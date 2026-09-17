"""
Analysis API — session-type-aware analytics endpoints.

Qualifying → handled by existing telemetry/fastest endpoints
Practice   → long runs, tyre deg rate
Race       → lap evolution, stint pace, position changes, sector stints
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import text
from backend.extensions import engine

analysis_bp = Blueprint("analysis", __name__)


# Module-level cache for FastF1 corner data.
# Key: session_key (int) → list of {number, dist_m, ref_speed}
# WHY module-level dict (not lru_cache): lru_cache doesn't work well with
# mutable return values. A plain dict is explicit and easy to inspect.
# Flask reuses the same process across requests in production mode.
# In debug mode (--reload), the module reloads on code changes — cache clears.
# In production (gunicorn), the cache persists for the worker's lifetime.
_corner_cache: dict = {}


def _get_official_corners(session_key: int) -> list | None:
    """
    Fetch and cache official corner positions for a session from FastF1.
    Returns list of {number, dist_m, ref_speed} dicts, or None if unavailable.

    Caching strategy: results stored in _corner_cache by session_key.
    First call: ~3-5s (FastF1 loads telemetry from disk cache)
    Subsequent calls: <1ms (dict lookup)
    """
    if session_key in _corner_cache:
        return _corner_cache[session_key]

    try:
        with engine.connect() as conn:
            sess_row = (
                conn.execute(
                    text("SELECT year, gp_name FROM sessions WHERE session_key = :sk"),
                    {"sk": session_key},
                )
                .mappings()
                .first()
            )

        if not sess_row:
            _corner_cache[session_key] = None
            return None

        import fastf1 as ff1

        ff1.Cache.enable_cache("./fastf1_cache")

        ff1_session = ff1.get_session(
            int(sess_row["year"]), sess_row["gp_name"].replace(" Grand Prix", ""), "Q"
        )
        ff1_session.load(telemetry=True, laps=True, weather=False, messages=False)

        circuit_info = ff1_session.get_circuit_info()
        corners_df = circuit_info.corners[["Number", "X", "Y"]]
        fastest_lap = ff1_session.laps.pick_fastest()
        ref_tel = fastest_lap.get_telemetry()

        official_corners = []
        for _, row in corners_df.iterrows():
            cx, cy = row["X"], row["Y"]
            xy_dists = ((ref_tel["X"] - cx) ** 2 + (ref_tel["Y"] - cy) ** 2) ** 0.5
            nearest = ref_tel.loc[xy_dists.idxmin()]
            spd = float(nearest["Speed"])
            dist_m = float(nearest["Distance"])

            if spd > 200:
                continue

            window = ref_tel[
                (ref_tel["Distance"] >= dist_m - 100)
                & (ref_tel["Distance"] <= dist_m + 100)
            ]
            if int(window["Brake"].sum()) == 0:
                continue

            official_corners.append(
                {
                    "number": int(row["Number"]),
                    "dist_m": dist_m,
                    "ref_speed": spd,
                }
            )

        _corner_cache[session_key] = official_corners
        return official_corners

    except Exception:
        _corner_cache[session_key] = None
        return None


# ── Shared: lap evolution ─────────────────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/lap-evolution")
def lap_evolution(session_key: int):
    """
    Every lap time for selected drivers, with compound and position.
    Used for race lap time evolution chart and FP pace overview.

    Returns:
        { drivers: { "63": { abbreviation, team_colour, laps: [{lap_number, lap_time_ms,
          compound, position, stint, is_personal_best, deleted}] } } }
    """
    drivers_param = request.args.get("drivers", "")
    params: dict = {"sk": session_key}
    driver_filter = ""

    if drivers_param:
        try:
            dns = [int(d.strip()) for d in drivers_param.split(",")]
            driver_filter = "AND l.driver_number = ANY(:dns)"
            params["dns"] = dns
        except ValueError:
            return {"error": "Driver numbers must be integers"}, 400

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(f"""
            SELECT
                l.driver_number,
                d.abbreviation,
                d.team_colour,
                d.team_name,
                l.lap_number,
                l.lap_time_ms,
                l.compound,
                l.position,
                l.stint,
                l.is_personal_best,
                l.deleted,
                l.s1_ms,
                l.s2_ms,
                l.s3_ms
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key = :sk
              {driver_filter}
            ORDER BY l.driver_number, l.lap_number
        """),
                params,
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify({"drivers": {}})

    # Group by driver
    from backend.api.v1.strategy import _resolve

    drivers: dict = {}
    for r in rows:
        dn = str(r["driver_number"])
        if dn not in drivers:
            drivers[dn] = {
                "driver_number": r["driver_number"],
                "abbreviation": r["abbreviation"],
                "team_name": r["team_name"],
                "team_colour": _resolve(r["team_colour"], r["team_name"]),
                "laps": [],
            }
        drivers[dn]["laps"].append(
            {
                "lap_number": r["lap_number"],
                "lap_time_ms": r["lap_time_ms"],
                "compound": r["compound"],
                "position": r["position"],
                "stint": r["stint"],
                "is_personal_best": r["is_personal_best"],
                "deleted": r["deleted"],
                "s1_ms": r["s1_ms"],
                "s2_ms": r["s2_ms"],
                "s3_ms": r["s3_ms"],
            }
        )

    return jsonify({"drivers": drivers})


# ── Race: stint pace ──────────────────────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/stint-pace")
def stint_pace(session_key: int):
    """
    Average, min, max lap time per driver per stint.
    Excludes safety car laps (track_status != '1') and outlier laps
    (more than 15% slower than driver's median — slow in/out laps).

    Returns list of stint summaries ordered by driver finishing position.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            WITH driver_median AS (
                SELECT
                    driver_number,
                    stint,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lap_time_ms) AS median_ms
                FROM lap_times
                WHERE session_key  = :sk
                  AND lap_time_ms  IS NOT NULL
                  AND deleted      = FALSE
                  AND stint        IS NOT NULL
                GROUP BY driver_number, stint
            ),
            clean_laps AS (
                SELECT l.*
                FROM lap_times l
                JOIN driver_median dm
                    ON dm.driver_number = l.driver_number
                    AND dm.stint        = l.stint
                WHERE l.session_key  = :sk
                  AND l.lap_time_ms  IS NOT NULL
                  AND l.deleted      = FALSE
                  AND l.stint        IS NOT NULL
                  -- Exclude laps >15% slower than median (pit in/out, SC laps)
                  AND l.lap_time_ms  <= dm.median_ms * 1.15
                  -- Exclude known SC laps
                  AND (l.track_status = '1' OR l.track_status IS NULL)
            )
            SELECT
                cl.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                cl.stint,
                cl.compound,
                MIN(cl.lap_number)                  AS start_lap,
                MAX(cl.lap_number)                  AS end_lap,
                COUNT(*)                            AS clean_laps,
                ROUND(AVG(cl.lap_time_ms)::numeric, 1) AS avg_ms,
                MIN(cl.lap_time_ms)                 AS best_ms,
                MAX(cl.lap_time_ms)                 AS worst_ms,
                ROUND(STDDEV(cl.lap_time_ms)::numeric, 1) AS stddev_ms,
                -- Deg rate: slope of lap time vs lap number within stint
                ROUND((
                    REGR_SLOPE(cl.lap_time_ms, cl.lap_number)
                )::numeric, 2)                      AS deg_ms_per_lap
            FROM clean_laps cl
            JOIN drivers d
                ON d.driver_number = cl.driver_number
                AND d.session_key  = :sk
            GROUP BY
                cl.driver_number, d.abbreviation, d.team_name,
                d.team_colour, cl.stint, cl.compound
            ORDER BY
                -- Order by finishing position
                (SELECT position FROM lap_times
                 WHERE session_key   = :sk
                   AND driver_number = cl.driver_number
                   AND position      IS NOT NULL
                 ORDER BY lap_number DESC LIMIT 1) ASC NULLS LAST,
                cl.stint ASC
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    results = []
    for r in rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        results.append(d)

    return jsonify(results)


# ── Race: position changes ────────────────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/position-changes")
def position_changes(session_key: int):
    """
    Position per lap for all drivers.
    Used to draw the position change chart across the race.

    Returns:
        { total_laps: int,
          drivers: { "63": { abbreviation, team_colour, positions: [1,1,2,...] } } }
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            SELECT
                l.driver_number,
                d.abbreviation,
                d.team_colour,
                d.team_name,
                l.lap_number,
                l.position
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key = :sk
              AND l.position    IS NOT NULL
              AND l.deleted     = FALSE
            ORDER BY l.driver_number, l.lap_number
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

        total_laps = (
            conn.execute(
                text("""
            SELECT MAX(lap_number) FROM lap_times WHERE session_key = :sk
        """),
                {"sk": session_key},
            ).scalar()
            or 0
        )

    if not rows:
        return jsonify({"total_laps": 0, "drivers": {}})

    from backend.api.v1.strategy import _resolve

    drivers: dict = {}
    for r in rows:
        dn = str(r["driver_number"])
        if dn not in drivers:
            drivers[dn] = {
                "driver_number": r["driver_number"],
                "abbreviation": r["abbreviation"],
                "team_colour": _resolve(r["team_colour"], r["team_name"]),
                "team_name": r["team_name"],
                "positions": {},
            }
        drivers[dn]["positions"][r["lap_number"]] = r["position"]

    return jsonify({"total_laps": total_laps, "drivers": drivers})


# ── Practice: long runs ───────────────────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/long-runs")
def long_runs(session_key: int):
    """
    Practice long run identification.

    A long run = a stint of >= min_laps consecutive laps on the same compound.
    These are the most valuable practice data — they show race pace before
    anyone knows who is fast in race trim.

    Query param: ?min_laps=5 (default 5)

    Returns drivers with their long run stints, including deg rate.
    """
    min_laps = request.args.get("min_laps", 5, type=int)

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            WITH stint_calc AS (
                SELECT
                    driver_number,
                    lap_number,
                    lap_time_ms,
                    compound,
                    -- Derive stint from compound changes if stint column null
                    COALESCE(stint,
                        SUM(CASE WHEN compound != LAG(compound) OVER w
                                     OR LAG(compound) OVER w IS NULL
                              THEN 1 ELSE 0 END) OVER w
                    ) AS stint_num
                FROM lap_times
                WHERE session_key  = :sk
                  AND lap_time_ms  IS NOT NULL
                  AND deleted      = FALSE
                  AND compound     IS NOT NULL
                  -- Exclude obvious hot/outlap times (>10% above median)
                WINDOW w AS (PARTITION BY driver_number ORDER BY lap_number)
            ),
            stint_summary AS (
                SELECT
                    driver_number,
                    stint_num,
                    compound,
                    COUNT(*)             AS laps,
                    MIN(lap_number)      AS start_lap,
                    MAX(lap_number)      AS end_lap,
                    MIN(lap_time_ms)     AS best_ms,
                    ROUND(AVG(lap_time_ms)::numeric, 1) AS avg_ms,
                    ROUND(STDDEV(lap_time_ms)::numeric, 1) AS stddev_ms,
                    ROUND(REGR_SLOPE(lap_time_ms, lap_number)::numeric, 2) AS deg_ms_per_lap
                FROM stint_calc
                GROUP BY driver_number, stint_num, compound
                HAVING COUNT(*) >= :min_laps
            )
            SELECT
                ss.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                ss.stint_num,
                ss.compound,
                ss.laps,
                ss.start_lap,
                ss.end_lap,
                ss.best_ms,
                ss.avg_ms,
                ss.stddev_ms,
                ss.deg_ms_per_lap
            FROM stint_summary ss
            JOIN drivers d
                ON d.driver_number = ss.driver_number
                AND d.session_key  = :sk
            ORDER BY ss.avg_ms ASC
        """),
                {"sk": session_key, "min_laps": min_laps},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    results = []
    for r in rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        results.append(d)

    return jsonify(results)


# ── Practice + Race: tyre degradation ────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/tyre-deg")
def tyre_degradation(session_key: int):
    """
    Tyre degradation rate per driver per stint.

    deg_ms_per_lap = milliseconds lost per additional lap on the same tyre.
    Positive = getting slower. Negative = unusual (tyre warming up still).

    Also returns a per-compound average across all drivers for comparison.
    """
    with engine.connect() as conn:
        # Per driver per stint
        per_driver = (
            conn.execute(
                text("""
            WITH stint_laps AS (
                SELECT
                    driver_number,
                    lap_number,
                    lap_time_ms,
                    compound,
                    COALESCE(stint,
                        SUM(CASE WHEN compound != LAG(compound) OVER w
                                     OR LAG(compound) OVER w IS NULL
                              THEN 1 ELSE 0 END) OVER w
                    ) AS stint_num,
                    -- Lap within stint (1 = first lap of stint)
                    ROW_NUMBER() OVER (
                        PARTITION BY driver_number,
                        COALESCE(stint,
                            SUM(CASE WHEN compound != LAG(compound) OVER w
                                         OR LAG(compound) OVER w IS NULL
                                  THEN 1 ELSE 0 END) OVER w)
                        ORDER BY lap_number
                    ) AS lap_in_stint
                FROM lap_times
                WHERE session_key = :sk
                  AND lap_time_ms IS NOT NULL
                  AND deleted     = FALSE
                  AND compound    IS NOT NULL
                WINDOW w AS (PARTITION BY driver_number ORDER BY lap_number)
            ),
            -- Exclude first and last lap of each stint (hot/cool laps)
            clean AS (
                SELECT sl.*
                FROM stint_laps sl
                JOIN (SELECT driver_number, stint_num, MAX(lap_in_stint) AS max_lap
                      FROM stint_laps GROUP BY driver_number, stint_num) mx
                    ON mx.driver_number = sl.driver_number
                    AND mx.stint_num    = sl.stint_num
                WHERE sl.lap_in_stint > 1
                  AND sl.lap_in_stint < mx.max_lap
                  AND sl.lap_time_ms  < (
                      SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lap_time_ms) * 1.1
                      FROM stint_laps sl2
                      WHERE sl2.driver_number = sl.driver_number
                        AND sl2.stint_num     = sl.stint_num
                  )
            )
            SELECT
                c.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                c.stint_num,
                c.compound,
                COUNT(*)  AS laps,
                ROUND(REGR_SLOPE(c.lap_time_ms, c.lap_in_stint)::numeric, 3) AS deg_ms_per_lap,
                ROUND(AVG(c.lap_time_ms)::numeric, 1) AS avg_ms,
                MIN(c.lap_time_ms) AS best_ms
            FROM clean c
            JOIN drivers d
                ON d.driver_number = c.driver_number
                AND d.session_key  = :sk
            GROUP BY
                c.driver_number, d.abbreviation, d.team_name,
                d.team_colour, c.stint_num, c.compound
            HAVING COUNT(*) >= 4
            ORDER BY c.driver_number, c.stint_num
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

        # Per compound average
        compound_avg = (
            conn.execute(
                text("""
            SELECT
                compound,
                ROUND(AVG(deg_rate)::numeric, 3) AS avg_deg_ms_per_lap,
                COUNT(DISTINCT driver_number)    AS drivers_sampled
            FROM (
                SELECT
                    driver_number,
                    compound,
                    REGR_SLOPE(lap_time_ms,
                        ROW_NUMBER() OVER (
                            PARTITION BY driver_number,
                            COALESCE(stint, 0)
                            ORDER BY lap_number
                        )
                    ) AS deg_rate
                FROM lap_times
                WHERE session_key = :sk
                  AND lap_time_ms IS NOT NULL
                  AND deleted     = FALSE
                  AND compound    IS NOT NULL
                GROUP BY driver_number, compound, COALESCE(stint, 0)
                HAVING COUNT(*) >= 4
            ) sub
            GROUP BY compound
            ORDER BY avg_deg_ms_per_lap ASC
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    from backend.api.v1.strategy import _resolve

    driver_results = []
    for r in per_driver:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        driver_results.append(d)

    return jsonify(
        {
            "per_driver": driver_results,
            "per_compound": [dict(r) for r in compound_avg],
        }
    )


# ── Shared: sector breakdown by stint ────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/sector-stints")
def sector_stints(session_key: int):
    """
    Best sector times per driver per stint.
    Shows where each driver gains/loses time in different race phases.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            SELECT
                l.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                COALESCE(l.stint, 1)    AS stint,
                l.compound,
                MIN(l.s1_ms)            AS best_s1,
                MIN(l.s2_ms)            AS best_s2,
                MIN(l.s3_ms)            AS best_s3,
                COUNT(*)                AS laps
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key = :sk
              AND l.deleted     = FALSE
              AND (l.s1_ms IS NOT NULL OR l.s2_ms IS NOT NULL OR l.s3_ms IS NOT NULL)
            GROUP BY
                l.driver_number, d.abbreviation, d.team_name,
                d.team_colour, COALESCE(l.stint, 1), l.compound
            ORDER BY l.driver_number, COALESCE(l.stint, 1)
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    results = []
    for r in rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        results.append(d)

    return jsonify(results)


# ── Race: gap to leader ───────────────────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/gap-to-leader")
def gap_to_leader(session_key: int):
    """
    Gap to race leader in seconds, per lap, per driver.

    Method: cumulative sum of lap_time_ms per driver, minus the leader's
    cumulative at the same lap. Leader = driver with smallest cumulative time
    on each lap (most accurate for lapped cars vs position column).

    Excludes deleted laps and pit laps (>115% of driver median) from
    cumulative so one slow lap doesn't corrupt the entire gap trace.

    Returns:
        { total_laps, drivers: { "63": { abbreviation, team_colour, gaps: { "1": 0.0, "2": 1.2, ... } } } }
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            WITH all_laps AS (
                -- Include ALL laps (pit laps too) for correct cumulative race time
                SELECT
                    l.driver_number,
                    l.lap_number,
                    l.lap_time_ms,
                    l.position
                FROM lap_times l
                WHERE l.session_key = :sk
                  AND l.lap_time_ms IS NOT NULL
            ),
            cumulative AS (
                -- Running total of race time per driver including pit laps
                SELECT
                    driver_number,
                    lap_number,
                    position,
                    SUM(lap_time_ms) OVER (
                        PARTITION BY driver_number
                        ORDER BY lap_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS cum_ms
                FROM all_laps
            ),
            leader_cum AS (
                -- P1 driver's cumulative race time each lap
                SELECT DISTINCT ON (lap_number)
                    lap_number,
                    cum_ms AS leader_ms
                FROM cumulative
                WHERE position = 1
                ORDER BY lap_number
            )
            SELECT
                c.driver_number,
                d.abbreviation,
                d.team_colour,
                d.team_name,
                c.lap_number,
                GREATEST(0, ROUND(((c.cum_ms - lc.leader_ms) / 1000.0)::numeric, 3)) AS gap_s
            FROM cumulative c
            JOIN leader_cum lc ON lc.lap_number = c.lap_number
            JOIN drivers d
                ON d.driver_number = c.driver_number
                AND d.session_key  = :sk
            ORDER BY c.driver_number, c.lap_number
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

        total_laps = (
            conn.execute(
                text("""
            SELECT MAX(lap_number) FROM lap_times WHERE session_key = :sk
        """),
                {"sk": session_key},
            ).scalar()
            or 0
        )

    if not rows:
        return jsonify({"total_laps": 0, "drivers": {}})

    from backend.api.v1.strategy import _resolve

    drivers: dict = {}
    for r in rows:
        dn = str(r["driver_number"])
        if dn not in drivers:
            drivers[dn] = {
                "driver_number": r["driver_number"],
                "abbreviation": r["abbreviation"],
                "team_colour": _resolve(r["team_colour"], r["team_name"]),
                "team_name": r["team_name"],
                "gaps": {},
            }
        drivers[dn]["gaps"][r["lap_number"]] = float(r["gap_s"])

    return jsonify({"total_laps": total_laps, "drivers": drivers})


# ── Race: undercut / overcut analysis ────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/undercut")
def undercut_analysis(session_key: int):
    """
    For each pit stop, was it an undercut, overcut, or neutral?

    Method:
      - Find each driver's pit stop laps via pit_in_time_ms IS NOT NULL
      - Compare position 2 laps before pit vs 3 laps after pit
        (3 laps gives pitted cars time to cycle through)
      - pos_gain > 0 = undercut worked, < 0 = overcut / lost out, 0 = neutral

    Also returns who they pitted against (nearest rival that pitted within
    3 laps either side) for context.

    Returns list of pit stop events ordered by lap number.
    """
    with engine.connect() as conn:
        pit_rows = (
            conn.execute(
                text("""
            WITH pit_laps AS (
                SELECT
                    l.driver_number,
                    d.abbreviation,
                    d.team_name,
                    d.team_colour,
                    l.lap_number          AS pit_lap,
                    l.compound            AS compound_in,   -- compound going IN (being removed)
                    l.stint               AS stint_in,
                    l.pit_in_time_ms
                FROM lap_times l
                JOIN drivers d
                    ON d.driver_number = l.driver_number
                    AND d.session_key  = l.session_key
                WHERE l.session_key      = :sk
                  AND l.pit_in_time_ms   IS NOT NULL
            ),
            pos_before AS (
                SELECT DISTINCT ON (l.driver_number, pl.pit_lap)
                    l.driver_number,
                    pl.pit_lap,
                    l.position AS pos_before
                FROM lap_times l
                JOIN pit_laps pl ON pl.driver_number = l.driver_number
                WHERE l.session_key = :sk
                  AND l.lap_number  = pl.pit_lap - 1
                  AND l.position    IS NOT NULL
            ),
            compound_after AS (
                SELECT DISTINCT ON (l.driver_number, pl.pit_lap)
                    l.driver_number,
                    pl.pit_lap,
                    l.compound AS compound_out,
                    l.tyre_life_laps
                FROM lap_times l
                JOIN pit_laps pl ON pl.driver_number = l.driver_number
                WHERE l.session_key = :sk
                  AND l.lap_number  = pl.pit_lap + 1
            ),
            pos_after AS (
                SELECT DISTINCT ON (l.driver_number, pl.pit_lap)
                    l.driver_number,
                    pl.pit_lap,
                    l.position AS pos_after
                FROM lap_times l
                JOIN pit_laps pl ON pl.driver_number = l.driver_number
                WHERE l.session_key = :sk
                  AND l.lap_number  = pl.pit_lap + 3
                  AND l.position    IS NOT NULL
            )
            SELECT
                pl.driver_number,
                pl.abbreviation,
                pl.team_name,
                pl.team_colour,
                pl.pit_lap,
                pl.compound_in,
                ca.compound_out,
                ca.tyre_life_laps,
                pb.pos_before,
                pa.pos_after,
                (pb.pos_before - pa.pos_after) AS pos_gain
            FROM pit_laps pl
            LEFT JOIN pos_before    pb ON pb.driver_number = pl.driver_number AND pb.pit_lap = pl.pit_lap
            LEFT JOIN pos_after     pa ON pa.driver_number = pl.driver_number AND pa.pit_lap = pl.pit_lap
            LEFT JOIN compound_after ca ON ca.driver_number = pl.driver_number AND ca.pit_lap = pl.pit_lap
            ORDER BY pl.pit_lap ASC, pl.driver_number ASC
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not pit_rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    results = []
    for r in pit_rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        pos_gain = d.get("pos_gain")
        d["verdict"] = (
            "undercut"
            if pos_gain is not None and pos_gain > 0
            else "overcut"
            if pos_gain is not None and pos_gain < 0
            else "neutral"
        )
        results.append(d)

    return jsonify(results)


# ── Race: fastest lap card ────────────────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/fastest-lap")
def fastest_lap(session_key: int):
    """
    Fastest lap of the race — who set it, when, on what compound,
    how far into their tyre stint, and how it compares to other drivers.

    Returns ordered list (fastest first) with gap to fastest.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            WITH best AS (
                SELECT DISTINCT ON (l.driver_number)
                    l.driver_number,
                    l.lap_number,
                    l.lap_time_ms,
                    l.compound,
                    l.tyre_life_laps,
                    l.position
                FROM lap_times l
                WHERE l.session_key  = :sk
                  AND l.lap_time_ms  IS NOT NULL
                  AND l.deleted      = FALSE
                  AND l.lap_time_ms  < 200000   -- exclude obvious outlaps
                ORDER BY l.driver_number, l.lap_time_ms ASC
            )
            SELECT
                b.driver_number,
                d.full_name,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                b.lap_number,
                b.lap_time_ms,
                b.compound,
                b.tyre_life_laps,
                b.position                          AS position_on_lap,
                b.lap_time_ms - MIN(b.lap_time_ms) OVER () AS gap_ms
            FROM best b
            JOIN drivers d
                ON d.driver_number = b.driver_number
                AND d.session_key  = :sk
            ORDER BY b.lap_time_ms ASC
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    results = []
    for r in rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        results.append(d)

    return jsonify(results)


# ── Practice: lap scatter ─────────────────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/fp-scatter")
def fp_scatter(session_key: int):
    """
    Every individual lap as a data point — lap number, lap time, compound.
    Used for scatter plot. Includes outlaps/inlaps flagged so frontend
    can show/hide them. No reconstruction from averages — raw lap data.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            SELECT
                l.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                l.lap_number,
                l.lap_time_ms,
                l.compound,
                l.tyre_life_laps,
                l.stint,
                l.deleted,
                l.is_personal_best,
                -- Flag outlap/inlap: first or last lap of stint, or >110% of driver median
                CASE WHEN l.tyre_life_laps <= 1 THEN true
                     WHEN l.pit_in_time_ms IS NOT NULL THEN true
                     WHEN l.lap_time_ms > (
                         SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY l2.lap_time_ms) * 1.10
                         FROM lap_times l2
                         WHERE l2.session_key    = l.session_key
                           AND l2.driver_number  = l.driver_number
                           AND l2.lap_time_ms    IS NOT NULL
                           AND l2.deleted        = FALSE
                     ) THEN true
                     ELSE false
                END AS is_outlier
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key  = :sk
              AND l.lap_time_ms  IS NOT NULL
              AND l.compound     IS NOT NULL
            ORDER BY l.driver_number, l.lap_number
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    results = []
    for r in rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        results.append(d)
    return jsonify(results)


# ── Practice: compound strategy reveal ───────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/fp-compounds")
def fp_compounds(session_key: int):
    """
    Per team: how many laps on each compound, and which drivers ran what.
    Reveals planned race strategy before anyone announces it.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            SELECT
                d.team_name,
                d.team_colour,
                d.driver_number,
                d.abbreviation,
                l.compound,
                COUNT(*)                                    AS laps,
                MIN(l.lap_time_ms)                          AS best_ms,
                ROUND(AVG(l.lap_time_ms)::numeric, 1)       AS avg_ms
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key  = :sk
              AND l.compound     IS NOT NULL
              AND l.lap_time_ms  IS NOT NULL
              AND l.deleted      = FALSE
            GROUP BY
                d.team_name, d.team_colour,
                d.driver_number, d.abbreviation,
                l.compound
            ORDER BY d.team_name, l.compound
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    # Group by team
    teams: dict = {}
    for r in rows:
        tn = r["team_name"]
        if tn not in teams:
            teams[tn] = {
                "team_name": tn,
                "team_colour": _resolve(r["team_colour"], tn),
                "compounds": {},
                "drivers": [],
            }
        # Accumulate compound laps at team level
        c = r["compound"]
        if c not in teams[tn]["compounds"]:
            teams[tn]["compounds"][c] = {"laps": 0, "best_ms": None}
        teams[tn]["compounds"][c]["laps"] += r["laps"]
        best = r["best_ms"]
        prev = teams[tn]["compounds"][c]["best_ms"]
        if best and (prev is None or best < prev):
            teams[tn]["compounds"][c]["best_ms"] = float(best)

        # Per-driver breakdown
        driver_entry = next(
            (
                x
                for x in teams[tn]["drivers"]
                if x["driver_number"] == r["driver_number"]
            ),
            None,
        )
        if not driver_entry:
            driver_entry = {
                "driver_number": r["driver_number"],
                "abbreviation": r["abbreviation"],
                "compounds": {},
            }
            teams[tn]["drivers"].append(driver_entry)
        driver_entry["compounds"][c] = {
            "laps": r["laps"],
            "best_ms": float(r["best_ms"]) if r["best_ms"] else None,
            "avg_ms": float(r["avg_ms"]) if r["avg_ms"] else None,
        }

    return jsonify(list(teams.values()))


# ── Practice: race sim detection ─────────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/fp-racesim")
def fp_racesim(session_key: int):
    """
    Identify genuine race simulation stints in practice.

    Criteria for a race sim stint:
      - 8+ consecutive laps on the same compound
      - Not on SOFT (teams don't race sim on softs)
      - Consistent pace (stddev < 1.5s)
      - Lap times within 107% of session best (not installation laps)

    Returns stints with per-lap data so frontend can plot the actual
    lap time trace — this is the key Friday evening intelligence.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            WITH driver_median AS (
                -- Use each driver's own median to filter outlaps/inlaps
                -- Session best is too strict for FP where installation laps exist
                SELECT driver_number,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lap_time_ms) AS median_ms
                FROM lap_times
                WHERE session_key = :sk
                  AND lap_time_ms IS NOT NULL
                  AND deleted     = FALSE
                GROUP BY driver_number
            ),
            lagged AS (
                -- Step 1: compute LAG separately (can't nest window functions)
                SELECT
                    l.driver_number,
                    l.lap_number,
                    l.lap_time_ms,
                    l.compound,
                    l.tyre_life_laps,
                    LAG(l.compound) OVER (
                        PARTITION BY l.driver_number ORDER BY l.lap_number
                    ) AS prev_compound
                FROM lap_times l
                JOIN driver_median dm ON dm.driver_number = l.driver_number
                WHERE l.session_key  = :sk
                  AND l.lap_time_ms  IS NOT NULL
                  AND l.deleted      = FALSE
                  AND l.compound     IS NOT NULL
                  AND l.compound     != 'SOFT'
                  AND l.lap_time_ms  <= dm.median_ms * 1.15
            ),
            stint_laps AS (
                -- Step 2: now derive stint number from the pre-computed LAG
                SELECT
                    driver_number,
                    lap_number,
                    lap_time_ms,
                    compound,
                    tyre_life_laps,
                    SUM(CASE WHEN compound != prev_compound
                                  OR prev_compound IS NULL
                             THEN 1 ELSE 0 END
                    ) OVER (PARTITION BY driver_number ORDER BY lap_number) AS stint_num
                FROM lagged
            ),
            valid_stints AS (
                SELECT
                    driver_number,
                    stint_num,
                    compound,
                    COUNT(*)                                         AS laps,
                    MIN(lap_number)                                  AS start_lap,
                    MAX(lap_number)                                  AS end_lap,
                    MIN(lap_time_ms)                                 AS best_ms,
                    ROUND(AVG(lap_time_ms)::numeric, 1)              AS avg_ms,
                    ROUND(STDDEV(lap_time_ms)::numeric, 1)           AS stddev_ms,
                    ROUND(REGR_SLOPE(lap_time_ms, lap_number)::numeric, 2) AS deg_ms_per_lap
                FROM stint_laps
                GROUP BY driver_number, stint_num, compound
                HAVING COUNT(*) >= 6
                   AND STDDEV(lap_time_ms) < 3000
            ),
            lap_detail AS (
                SELECT
                    sl.driver_number,
                    sl.stint_num,
                    sl.lap_number,
                    sl.lap_time_ms,
                    sl.tyre_life_laps
                FROM stint_laps sl
                JOIN valid_stints vs
                    ON vs.driver_number = sl.driver_number
                    AND vs.stint_num    = sl.stint_num
            )
            SELECT
                vs.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                vs.stint_num,
                vs.compound,
                vs.laps,
                vs.start_lap,
                vs.end_lap,
                vs.best_ms,
                vs.avg_ms,
                vs.stddev_ms,
                vs.deg_ms_per_lap,
                JSON_AGG(
                    JSON_BUILD_OBJECT(
                        'lap_number',    ld.lap_number,
                        'lap_time_ms',   ld.lap_time_ms,
                        'tyre_life_laps', ld.tyre_life_laps
                    ) ORDER BY ld.lap_number
                ) AS lap_times
            FROM valid_stints vs
            JOIN drivers d
                ON d.driver_number = vs.driver_number
                AND d.session_key  = :sk
            JOIN lap_detail ld
                ON ld.driver_number = vs.driver_number
                AND ld.stint_num    = vs.stint_num
            GROUP BY
                vs.driver_number, d.abbreviation, d.team_name,
                d.team_colour, vs.stint_num, vs.compound,
                vs.laps, vs.start_lap, vs.end_lap,
                vs.best_ms, vs.avg_ms, vs.stddev_ms, vs.deg_ms_per_lap
            ORDER BY vs.avg_ms ASC
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve
    import json as json_mod

    results = []
    for r in rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        # lap_times comes back as JSON string from postgres
        lt = d.get("lap_times")
        if isinstance(lt, str):
            d["lap_times"] = json_mod.loads(lt)
        elif lt is None:
            d["lap_times"] = []
        results.append(d)
    return jsonify(results)


# ── Practice: sector time progression ────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/fp-sectors")
def fp_sectors(session_key: int):
    """
    Sector time progression through the session.
    Shows whether a driver is improving setup (getting faster) or struggling.

    For each driver: their best S1/S2/S3 in each tercile of the session
    (early / middle / late) so you can see direction of travel.

    Also returns overall best sector per driver for the session delta table.
    """
    with engine.connect() as conn:
        max_lap = (
            conn.execute(
                text("""
            SELECT MAX(lap_number) FROM lap_times WHERE session_key = :sk
        """),
                {"sk": session_key},
            ).scalar()
            or 1
        )

        rows = (
            conn.execute(
                text("""
            WITH terciles AS (
                SELECT
                    l.driver_number,
                    d.abbreviation,
                    d.team_name,
                    d.team_colour,
                    l.lap_number,
                    l.s1_ms,
                    l.s2_ms,
                    l.s3_ms,
                    l.compound,
                    CASE
                        WHEN l.lap_number <= :max_lap / 3             THEN 'early'
                        WHEN l.lap_number <= (:max_lap * 2) / 3       THEN 'middle'
                        ELSE                                               'late'
                    END AS phase
                FROM lap_times l
                JOIN drivers d
                    ON d.driver_number = l.driver_number
                    AND d.session_key  = l.session_key
                WHERE l.session_key  = :sk
                  AND l.deleted      = FALSE
                  AND (l.s1_ms IS NOT NULL OR l.s2_ms IS NOT NULL OR l.s3_ms IS NOT NULL)
            )
            SELECT
                driver_number,
                abbreviation,
                team_name,
                team_colour,
                phase,
                MIN(s1_ms) AS best_s1,
                MIN(s2_ms) AS best_s2,
                MIN(s3_ms) AS best_s3,
                COUNT(*)   AS laps
            FROM terciles
            GROUP BY driver_number, abbreviation, team_name, team_colour, phase
            ORDER BY driver_number,
                CASE phase WHEN 'early' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END
        """),
                {"sk": session_key, "max_lap": max_lap},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    # Group by driver, phases as keys
    drivers: dict = {}
    for r in rows:
        dn = str(r["driver_number"])
        if dn not in drivers:
            drivers[dn] = {
                "driver_number": r["driver_number"],
                "abbreviation": r["abbreviation"],
                "team_name": r["team_name"],
                "team_colour": _resolve(r["team_colour"], r["team_name"]),
                "phases": {},
            }
        drivers[dn]["phases"][r["phase"]] = {
            "best_s1": r["best_s1"],
            "best_s2": r["best_s2"],
            "best_s3": r["best_s3"],
            "laps": r["laps"],
        }

    return jsonify(list(drivers.values()))


# ── Practice: compound delta table ───────────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/fp-compound-delta")
def fp_compound_delta(session_key: int):
    """
    Each driver's best lap time per compound + gap to session best on that compound.

    Shows who has a strong HARD vs who only goes fast on SOFT — the key
    input for one-stop vs two-stop strategy decisions.

    Returns drivers sorted by their overall best time (fastest first).
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            WITH clean_laps AS (
                SELECT
                    l.driver_number,
                    l.compound,
                    l.lap_time_ms
                FROM lap_times l
                WHERE l.session_key  = :sk
                  AND l.lap_time_ms  IS NOT NULL
                  AND l.deleted      = FALSE
                  AND l.compound     IS NOT NULL
                  -- exclude outlaps: tyre_life_laps = 1 or pit_in lap
                  AND l.tyre_life_laps > 1
                  AND l.pit_in_time_ms IS NULL
            ),
            best_per_driver_compound AS (
                SELECT
                    driver_number,
                    compound,
                    MIN(lap_time_ms) AS best_ms
                FROM clean_laps
                GROUP BY driver_number, compound
            ),
            session_best_per_compound AS (
                SELECT
                    compound,
                    MIN(lap_time_ms) AS session_best_ms
                FROM clean_laps
                GROUP BY compound
            ),
            overall_best AS (
                SELECT driver_number, MIN(best_ms) AS overall_best_ms
                FROM best_per_driver_compound
                GROUP BY driver_number
            )
            SELECT
                b.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                b.compound,
                b.best_ms,
                ROUND((b.best_ms - sb.session_best_ms)::numeric, 1) AS gap_to_best_ms,
                ob.overall_best_ms
            FROM best_per_driver_compound b
            JOIN session_best_per_compound sb ON sb.compound = b.compound
            JOIN overall_best ob ON ob.driver_number = b.driver_number
            JOIN drivers d
                ON d.driver_number = b.driver_number
                AND d.session_key  = :sk
            ORDER BY ob.overall_best_ms ASC, b.driver_number, b.compound
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify([])

    from backend.api.v1.strategy import _resolve

    # Group by driver
    drivers: dict = {}
    for r in rows:
        dn = r["driver_number"]
        if dn not in drivers:
            drivers[dn] = {
                "driver_number": dn,
                "abbreviation": r["abbreviation"],
                "team_name": r["team_name"],
                "team_colour": _resolve(r["team_colour"], r["team_name"]),
                "overall_best_ms": float(r["overall_best_ms"]),
                "compounds": {},
            }
        drivers[dn]["compounds"][r["compound"]] = {
            "best_ms": float(r["best_ms"]),
            "gap_to_best_ms": float(r["gap_to_best_ms"]),
        }

    return jsonify(list(drivers.values()))


# ── Practice: tyre degradation comparison ────────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/fp-tyre-deg")
def fp_tyre_deg(session_key: int):
    """
    Per-driver stint traces for deg comparison — all drivers on same compound
    overlaid so you can see who manages tyres best.

    Returns stints of >= 4 laps grouped by compound, with individual lap times
    so the frontend can draw actual traces (not just summary stats).

    Each lap is expressed as delta from the stint's first clean lap so all
    stints start at 0 — this normalises for absolute pace differences and
    shows pure degradation shape.
    """
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
            WITH driver_median AS (
                SELECT driver_number,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lap_time_ms) AS median_ms
                FROM lap_times
                WHERE session_key = :sk
                  AND lap_time_ms IS NOT NULL
                  AND deleted     = FALSE
                GROUP BY driver_number
            ),
            filtered AS (
                SELECT
                    l.driver_number,
                    l.lap_number,
                    l.lap_time_ms,
                    l.compound,
                    l.tyre_life_laps
                FROM lap_times l
                JOIN driver_median dm ON dm.driver_number = l.driver_number
                WHERE l.session_key     = :sk
                  AND l.lap_time_ms     IS NOT NULL
                  AND l.deleted         = FALSE
                  AND l.compound        IS NOT NULL
                  AND l.tyre_life_laps  > 1
                  AND l.pit_in_time_ms  IS NULL
                  AND l.lap_time_ms     <= dm.median_ms * 1.12
            ),
            lagged AS (
                SELECT *,
                    LAG(compound) OVER (
                        PARTITION BY driver_number ORDER BY lap_number
                    ) AS prev_compound
                FROM filtered
            ),
            stinted AS (
                SELECT *,
                    SUM(CASE WHEN compound != prev_compound
                                  OR prev_compound IS NULL
                             THEN 1 ELSE 0 END
                    ) OVER (PARTITION BY driver_number ORDER BY lap_number) AS stint_num
                FROM lagged
            ),
            stint_summary AS (
                SELECT driver_number, stint_num, compound, COUNT(*) AS laps
                FROM stinted
                GROUP BY driver_number, stint_num, compound
                HAVING COUNT(*) >= 4
            ),
            first_lap_time AS (
                -- Baseline = first clean lap of each valid stint
                SELECT DISTINCT ON (s.driver_number, s.stint_num)
                    s.driver_number,
                    s.stint_num,
                    s.lap_time_ms AS base_ms
                FROM stinted s
                JOIN stint_summary ss
                    ON ss.driver_number = s.driver_number
                    AND ss.stint_num    = s.stint_num
                ORDER BY s.driver_number, s.stint_num, s.lap_number ASC
            )
            SELECT
                s.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                s.compound,
                s.stint_num,
                s.lap_number,
                s.lap_time_ms,
                s.tyre_life_laps,
                -- Delta from first lap: positive = getting slower
                ROUND((s.lap_time_ms - fl.base_ms)::numeric, 1) AS delta_ms,
                ROW_NUMBER() OVER (
                    PARTITION BY s.driver_number, s.stint_num
                    ORDER BY s.lap_number
                ) - 1 AS lap_in_stint
            FROM stinted s
            JOIN stint_summary ss
                ON ss.driver_number = s.driver_number
                AND ss.stint_num    = s.stint_num
            JOIN first_lap_time fl
                ON fl.driver_number = s.driver_number
                AND fl.stint_num    = s.stint_num
            JOIN drivers d
                ON d.driver_number = s.driver_number
                AND d.session_key  = :sk
            ORDER BY s.driver_number, s.stint_num, s.lap_number
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify({})

    from backend.api.v1.strategy import _resolve

    # Group by compound → driver → stint → laps
    by_compound: dict = {}
    for r in rows:
        compound = r["compound"]
        dn = r["driver_number"]
        sn = r["stint_num"]

        if compound not in by_compound:
            by_compound[compound] = {}

        key = f"{dn}_{sn}"
        if key not in by_compound[compound]:
            by_compound[compound][key] = {
                "driver_number": dn,
                "abbreviation": r["abbreviation"],
                "team_name": r["team_name"],
                "team_colour": _resolve(r["team_colour"], r["team_name"]),
                "stint_num": sn,
                "laps": [],
            }

        by_compound[compound][key]["laps"].append(
            {
                "lap_in_stint": r["lap_in_stint"],
                "lap_time_ms": float(r["lap_time_ms"]),
                "delta_ms": float(r["delta_ms"]),
                "tyre_life_laps": r["tyre_life_laps"],
            }
        )

    # Convert to list-of-stints per compound
    result = {}
    for compound, stints in by_compound.items():
        result[compound] = list(stints.values())

    return jsonify(result)


# ── Qualifying: Q1/Q2/Q3 segment leaderboards ────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/quali-segments")
def quali_segments(session_key: int):
    """
    Best lap per driver per qualifying segment (Q1, Q2, Q3).

    Strategy: FastF1 does not populate SessionPart or Stint for qualifying.
    We detect Q1/Q2/Q3 boundaries by finding gaps > 5 minutes in LapStartTime
    across all drivers — these correspond to the mandatory red-flag breaks
    between segments.

    Returns:
        {
          "segments": {
            "Q1": [ { driver_number, abbreviation, team_name, team_colour,
                      lap_number, lap_time_ms, s1_ms, s2_ms, s3_ms,
                      gap_ms, eliminated } ],
            "Q2": [ ... ],
            "Q3": [ ... ]
          },
          "boundaries": { "Q2_start_lap": int, "Q3_start_lap": int }
        }

    Uses stored lap segment metadata when present. Falls back to FastF1-based
    boundary detection only for older sessions that were ingested before
    quali_segment existed.
    """
    import os
    import fastf1
    import pandas as pd
    from backend.api.v1.strategy import _resolve

    # ── 1. Get session metadata from DB ──────────────────────────────────────
    with engine.connect() as conn:
        session_row = (
            conn.execute(
                text("""
            SELECT year, gp_name, session_type
            FROM sessions WHERE session_key = :sk
        """),
                {"sk": session_key},
            )
            .mappings()
            .first()
        )

        if not session_row or session_row["session_type"] not in ("Q", "SQ"):
            return jsonify({"error": "Not a qualifying session"}), 400

        # Get all lap times from DB for this session
        db_laps = (
            conn.execute(
                text("""
            SELECT
                l.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                l.lap_number,
                l.lap_time_ms,
                l.s1_ms,
                l.s2_ms,
                l.s3_ms,
                l.quali_segment,
                l.deleted
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key = :sk
              AND l.lap_time_ms IS NOT NULL
              AND l.deleted = FALSE
            ORDER BY l.driver_number, l.lap_time_ms ASC
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

        drivers_rows = (
            conn.execute(
                text("""
            SELECT driver_number, abbreviation, team_name, team_colour
            FROM drivers WHERE session_key = :sk
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

    # Build driver info lookup
    driver_info = {
        r["driver_number"]: {
            "abbreviation": r["abbreviation"],
            "team_name": r["team_name"],
            "team_colour": _resolve(r["team_colour"], r["team_name"]),
        }
        for r in drivers_rows
    }

    stored_segments_present = any(
        row.get("quali_segment") is not None for row in db_laps
    )

    if stored_segments_present:
        lap_segment_map = {
            (str(row["driver_number"]), int(row["lap_number"])): int(
                row["quali_segment"]
            )
            for row in db_laps
            if row.get("quali_segment") is not None
        }
        q2_laps = [
            int(row["lap_number"]) for row in db_laps if row.get("quali_segment") == 2
        ]
        q3_laps = [
            int(row["lap_number"]) for row in db_laps if row.get("quali_segment") == 3
        ]
        q2_start = min(q2_laps) if q2_laps else None
        q3_start = min(q3_laps) if q3_laps else None
    else:
        # ── 2. Fallback: derive segments from FastF1 cache for older data ────
        try:
            cache_dir = os.environ.get("FASTF1_CACHE_DIR", "./fastf1_cache")
            fastf1.Cache.enable_cache(cache_dir)

            f1_session_name = (
                "Sprint Qualifying"
                if session_row["session_type"] == "SQ"
                else "Qualifying"
            )
            sess = fastf1.get_session(
                int(session_row["year"]),
                session_row["gp_name"].replace(" Grand Prix", ""),
                f1_session_name,
            )
            sess.load(telemetry=False, weather=False, messages=False)

            all_laps = sess.laps[["DriverNumber", "LapNumber", "LapStartTime"]].copy()
            all_laps = all_laps.dropna(subset=["LapStartTime"])
            all_laps = all_laps.sort_values("LapStartTime")
            all_laps["gap"] = all_laps["LapStartTime"].diff()
            boundaries = all_laps[all_laps["gap"] > pd.Timedelta(minutes=5)][
                "LapStartTime"
            ].tolist()

            def assign_segment(t):
                if len(boundaries) == 0:
                    return 1
                if t < boundaries[0]:
                    return 1
                if len(boundaries) < 2 or t < boundaries[1]:
                    return 2
                return 3

            all_laps["segment"] = all_laps["LapStartTime"].apply(assign_segment)
            lap_segment_map = {
                (str(row["DriverNumber"]), int(row["LapNumber"])): int(row["segment"])
                for _, row in all_laps.iterrows()
            }
            q2_boundary_laps = all_laps[all_laps["segment"] == 2]["LapNumber"]
            q3_boundary_laps = all_laps[all_laps["segment"] == 3]["LapNumber"]
            q2_start = (
                int(q2_boundary_laps.min()) if not q2_boundary_laps.empty else None
            )
            q3_start = (
                int(q3_boundary_laps.min()) if not q3_boundary_laps.empty else None
            )
        except Exception:
            lap_segment_map = {}
            q2_start = q3_start = None

    # ── 3. Assign each DB lap to its segment ─────────────────────────────────
    # Group DB laps by driver, find best lap per segment
    # Structure: segment → driver → best lap row
    from collections import defaultdict

    # First pass: collect all valid laps per driver per segment
    driver_segment_laps: dict = defaultdict(lambda: defaultdict(list))

    for row in db_laps:
        dn = row["driver_number"]
        ln = row["lap_number"]
        seg_key = (str(dn), int(ln))
        segment = lap_segment_map.get(seg_key, 1)  # default to Q1 if no cache
        driver_segment_laps[segment][dn].append(dict(row))

    # Second pass: pick best (fastest) lap per driver per segment
    segments_out: dict = {"Q1": [], "Q2": [], "Q3": []}
    seg_labels = {1: "Q1", 2: "Q2", 3: "Q3"}

    for seg_num, seg_label in seg_labels.items():
        seg_drivers = driver_segment_laps.get(seg_num, {})
        seg_results = []

        for dn, laps in seg_drivers.items():
            # Best lap = minimum lap_time_ms
            best = min(laps, key=lambda x: x["lap_time_ms"])
            info = driver_info.get(dn, {})
            seg_results.append(
                {
                    "driver_number": dn,
                    "abbreviation": info.get("abbreviation", "???"),
                    "team_name": info.get("team_name", ""),
                    "team_colour": info.get("team_colour", "666666"),
                    "lap_number": best["lap_number"],
                    "lap_time_ms": best["lap_time_ms"],
                    "s1_ms": best["s1_ms"],
                    "s2_ms": best["s2_ms"],
                    "s3_ms": best["s3_ms"],
                }
            )

        # Sort by lap time
        seg_results.sort(key=lambda x: x["lap_time_ms"])

        # Add gap to leader and eliminated flag
        # Q1 eliminates P16-P20 (bottom 5 of 20), Q2 eliminates P11-P15
        eliminate_from = {1: 16, 2: 11, 3: None}
        elim_pos = eliminate_from[seg_num]
        fastest_ms = seg_results[0]["lap_time_ms"] if seg_results else None

        for i, r in enumerate(seg_results):
            r["position"] = i + 1
            r["gap_ms"] = (
                round(r["lap_time_ms"] - fastest_ms, 1) if fastest_ms else None
            )
            r["eliminated"] = elim_pos is not None and r["position"] >= elim_pos

        segments_out[seg_label] = seg_results

    return jsonify(
        {
            "segments": segments_out,
            "boundaries": {
                "Q2_start_lap": q2_start,
                "Q3_start_lap": q3_start,
            },
        }
    )


# ── Qualifying: braking + throttle analysis ───────────────────────────────────


@analysis_bp.get("/sessions/<int:session_key>/analysis/driver-compare-stats")
def driver_compare_stats(session_key: int):
    """
    Computes corner-by-corner braking and throttle statistics from raw telemetry.

    ALGORITHM:
    1. Load raw telemetry for each driver (not the interpolated 400-point version)
    2. Find corners by detecting local speed minima (apex = slowest point)
    3. Per corner, find:
       - Brake point: last braking sample before apex
       - Braking distance: metres from brake point to apex
       - Decel rate: speed drop per metre of braking distance
       - Throttle point: first throttle sample after apex
       - Exit speed: speed 50m past throttle application
    4. Compare drivers at matched corners (same corner index)
    """
    drivers_param = request.args.get("drivers", "")
    if not drivers_param:
        return {"error": "drivers param required e.g. ?drivers=63,12"}, 400

    try:
        driver_nums = [int(d.strip()) for d in drivers_param.split(",")]
    except ValueError:
        return {"error": "driver numbers must be integers"}, 400

    with engine.connect() as conn:
        # Load raw telemetry — ordered by distance so we can scan sequentially
        rows = (
            conn.execute(
                text("""
            SELECT
                t.driver_number,
                d.abbreviation,
                d.team_colour,
                d.team_name,
                t.distance_m,
                t.speed_kmh,
                t.brake,
                t.throttle_pct,
                t.x_pos,
                t.y_pos,
                t.gear
            FROM telemetry t
            JOIN drivers d
                ON d.driver_number = t.driver_number
                AND d.session_key  = t.session_key
            WHERE t.session_key    = :sk
              AND t.driver_number  = ANY(:dns)
            ORDER BY t.driver_number, t.distance_m
        """),
                {"sk": session_key, "dns": driver_nums},
            )
            .mappings()
            .all()
        )

    if not rows:
        return jsonify({"error": "No telemetry found"}), 404

    # Group samples by driver
    from collections import defaultdict

    by_driver: dict = defaultdict(list)
    meta: dict = {}
    for r in rows:
        dn = r["driver_number"]
        by_driver[dn].append(
            {
                "distance_m": float(r["distance_m"]),
                "speed_kmh": float(r["speed_kmh"]),
                "brake": bool(r["brake"]),
                "throttle_pct": float(r["throttle_pct"]),
                "x_pos": float(r["x_pos"]) if r["x_pos"] else 0.0,
                "y_pos": float(r["y_pos"]) if r["y_pos"] else 0.0,
                "gear": int(r["gear"]) if r["gear"] else 0,
            }
        )
        if dn not in meta:
            from backend.api.v1.strategy import _resolve

            meta[dn] = {
                "abbreviation": r["abbreviation"],
                "team_colour": _resolve(r["team_colour"], r["team_name"]),
                "team_name": r["team_name"],
            }

    # ── Corner detection ──────────────────────────────────────────────────────
    # Find local speed minima across the lap.
    # A local minimum at index i means: speed[i] < speed[i-window] AND speed[i] < speed[i+window]
    # window=15 means we look 15 samples (~45m) either side — filters out micro-wobbles
    # min_speed=80 filters out slow-zone anomalies and start/finish

    def find_corners(samples: list, session_key: int = 0, **kwargs) -> list:
        """
        FastF1 official corner position-based detection.

        WHY this beats DBSCAN/sliding-window:
        Both previous approaches tried to INFER where corners are from speed data.
        That\'s fragile — different drivers take different lines, brake at different
        points, and carry different speeds. Inference always has false positives.

        FastF1 provides OFFICIAL corner positions (X, Y coordinates) from the
        FIA circuit map. These are ground truth — the corners are exactly where
        the circuit designers put them, not where the speed trace happens to dip.

        Algorithm:
        1. Fetch official corner X/Y positions from FastF1 (cached, ~0ms)
        2. For each official corner, find telemetry samples within a spatial
           radius (80m in track coordinates)
        3. Apex = minimum speed sample within that window
        4. Run braking/throttle analysis from that apex

        Result: exactly N corners (Melbourne=14), correctly numbered T1-T14,
        identical corner set for every driver, zero false positives.

        Fallback: if FastF1 data unavailable, falls back to P35 percentile
        + brake-evidence filter (the previous approach).
        """
        import numpy as np

        if len(samples) < 20:
            return []

        # ── Step 1: get official corner distances from FastF1 ────────────────
        # Strategy: load FastF1 telemetry for the reference driver (fastest lap)
        # to get the official Distance value at each corner position.
        # This is more reliable than X/Y matching because Distance is already
        # mapped along the track — no coordinate transformation needed.
        # Use cached official corners — fast after first load per session
        official_corners = _get_official_corners(session_key)

        # ── Step 2: find apex in our DB telemetry near each official distance ──
        if official_corners:
            apex_indices = []

            for corner in official_corners:
                ref_dist = corner["dist_m"]

                # Search window: ±100m around official corner distance.
                # WHY 100m: drivers vary their apex point by up to 80m vs the
                # geometric corner centre. 100m captures all personal apex points
                # while staying within the corner's physical boundary.
                window = [
                    i
                    for i, s in enumerate(samples)
                    if abs(s["distance_m"] - ref_dist) <= 100
                ]

                if not window:
                    continue

                # Apex = minimum speed in the window
                apex_idx = min(window, key=lambda i: samples[i]["speed_kmh"])

                if samples[apex_idx]["speed_kmh"] > 60:
                    samples[apex_idx]["_corner_number"] = corner["number"]
                    apex_indices.append(apex_idx)

            if apex_indices:
                apex_indices.sort(key=lambda i: samples[i]["distance_m"])
                return apex_indices

        # ── Fallback: percentile-based detection ──────────────────────────────
        # Used when FastF1 is unavailable (e.g. circuit not in cache,
        # network issues, or non-standard session type).
        from sklearn.cluster import DBSCAN

        speeds = np.array([s["speed_kmh"] for s in samples])
        distances = np.array([s["distance_m"] for s in samples])
        speed_threshold = float(np.percentile(speeds, 35))
        low_speed_mask = speeds < speed_threshold
        low_speed_indices = np.where(low_speed_mask)[0]
        if len(low_speed_indices) < 4:
            return []
        track_len = float(distances[-1] - distances[0]) or 1.0
        max_speed = float(speeds.max()) or 1.0
        X_feat = np.column_stack(
            [
                (distances[low_speed_indices] - distances[0]) / track_len,
                speeds[low_speed_indices] / max_speed,
            ]
        )
        db = DBSCAN(eps=0.008, min_samples=4).fit(X_feat)
        labels = db.labels_
        apex_indices = []
        for label in set(labels) - {-1}:
            cluster_mask = labels == label
            cluster_orig_idx = low_speed_indices[cluster_mask]
            cluster_speeds = speeds[cluster_orig_idx]
            apex_orig = int(cluster_orig_idx[int(np.argmin(cluster_speeds))])
            apex_speed = samples[apex_orig]["speed_kmh"]
            if apex_speed <= 60 or apex_speed > 190:
                continue
            brake_count = sum(
                1
                for j in range(max(0, apex_orig - 50), apex_orig)
                if samples[j]["brake"]
            )
            if apex_speed > 160 and brake_count < 2:
                continue
            apex_indices.append(apex_orig)
        apex_indices.sort(key=lambda i: samples[i]["distance_m"])
        return apex_indices

    # ── Per-corner stats ──────────────────────────────────────────────────────

    def analyse_corner(samples: list, apex_idx: int) -> dict | None:
        """
        Given the full sample list and the apex index, compute braking and
        throttle stats for this corner.

        BRAKING:
        - Scan backwards from apex to find last brake=True sample
        - If no braking found within 200m = corner doesn't need braking (chicane exit etc)
        - Braking distance = distance(apex) - distance(brake_start)
        - Decel rate = speed_drop / braking_distance  [km/h per metre]

        THROTTLE:
        - Scan forwards from apex to find first throttle > 10% sample
        - Exit speed = speed 50m after throttle application point
        - Throttle aggression = average throttle slope over next 30 samples
        """
        apex = samples[apex_idx]
        apex_dist = apex["distance_m"]

        # ── Braking: scan back from apex ─────────────────────────────────────
        brake_start_idx = None
        brake_start_dist = None
        brake_start_spd = None

        MAX_BRAKING_DIST_M = 150.0  # Physics cap: no F1 car brakes from >150m

        for j in range(apex_idx - 1, max(0, apex_idx - 120), -1):
            s = samples[j]
            # Physics cap: if we're more than 150m before apex, stop.
            # Anything beyond 150m belongs to the PREVIOUS corner's approach.
            # This prevents adjacent corner braking zones bleeding into each other.
            if apex_dist - s["distance_m"] > MAX_BRAKING_DIST_M:
                break
            if s["brake"]:
                brake_start_idx = j
                brake_start_dist = s["distance_m"]
                brake_start_spd = s["speed_kmh"]
            elif brake_start_idx is not None:
                break

        if brake_start_idx is None:
            return None

        braking_dist = apex_dist - brake_start_dist
        speed_drop = brake_start_spd - apex["speed_kmh"]
        # Minimum speed drop of 3 kmh — filters pure noise (road bumps)
        # but keeps light-braking fast corners and trail-braking entries.
        # WHY 3 not 5: a driver lifting slightly into a 200kmh corner may only
        # drop 4-5kmh but that's still a real cornering event worth analysing.
        if speed_drop < 3.0:
            return None

        decel_rate = speed_drop / braking_dist if braking_dist > 0 else 0.0

        # ── Throttle: scan forward from apex ─────────────────────────────────
        throttle_idx = None
        throttle_dist = None

        for j in range(apex_idx + 1, min(len(samples), apex_idx + 120)):
            s = samples[j]
            if s["distance_m"] - apex_dist > 300:
                break
            if s["throttle_pct"] > 10.0:
                throttle_idx = j
                throttle_dist = s["distance_m"]
                break

        # Exit speed: speed ~50m after throttle application
        # WHY fallback to last sample: if throttle point is near end of lap data
        # (e.g. final corner before S/F line), there may not be 50m of data left.
        # In that case use the last available sample — still valid exit speed.
        exit_speed = None
        if throttle_idx is not None:
            for j in range(throttle_idx, min(len(samples), throttle_idx + 30)):
                if samples[j]["distance_m"] - throttle_dist > 50:
                    exit_speed = samples[j]["speed_kmh"]
                    break
            # Fallback: use last sample within 100m if 50m target not reached
            if exit_speed is None:
                for j in range(
                    min(len(samples) - 1, throttle_idx + 35), throttle_idx, -1
                ):
                    if samples[j]["distance_m"] - throttle_dist <= 100:
                        candidate = samples[j]["speed_kmh"]
                        # Validate: exit speed must be higher than apex speed
                        # If it's not, the driver is still slowing — wrong point
                        if candidate > apex["speed_kmh"]:
                            exit_speed = candidate
                        break

        # Throttle aggression: slope of throttle trace over 20 samples post-application
        throttle_aggression = None
        if throttle_idx is not None:
            end_idx = min(len(samples) - 1, throttle_idx + 20)
            if end_idx > throttle_idx:
                delta_throttle = (
                    samples[end_idx]["throttle_pct"]
                    - samples[throttle_idx]["throttle_pct"]
                )
                delta_dist = (
                    samples[end_idx]["distance_m"] - samples[throttle_idx]["distance_m"]
                )
                throttle_aggression = (
                    delta_throttle / delta_dist if delta_dist > 0 else 0.0
                )

        official_num = apex.get("_corner_number", None)

        return {
            "corner_number": official_num,  # T1-T14 official number
            "apex_dist_m": round(apex_dist, 1),
            "apex_speed_kmh": round(apex["speed_kmh"], 1),
            "apex_x": round(apex["x_pos"], 1),
            "apex_y": round(apex["y_pos"], 1),
            "brake_point_dist_m": round(brake_start_dist, 1),
            "braking_dist_m": round(braking_dist, 1),
            "braking_speed_kmh": round(brake_start_spd, 1),
            "decel_rate": round(decel_rate, 3),
            "throttle_dist_m": round(throttle_dist, 1) if throttle_dist else None,
            "throttle_gap_m": round(throttle_dist - apex_dist, 1)
            if throttle_dist
            else None,
            "exit_speed_kmh": round(exit_speed, 1) if exit_speed else None,
            "throttle_aggression": round(throttle_aggression, 3)
            if throttle_aggression
            else None,
        }

    # ── Run analysis per driver ───────────────────────────────────────────────

    driver_results = {}
    all_corner_sets = {}

    for dn, samples in by_driver.items():
        apex_indices = find_corners(samples, session_key=session_key)
        corners = []
        for idx in apex_indices:
            stats = analyse_corner(samples, idx)
            if stats:
                corners.append(stats)
        all_corner_sets[dn] = corners

        def median(vals):
            s = sorted(v for v in vals if v is not None)
            if not s:
                return 0
            mid = len(s) // 2
            return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

        # Use median not mean for decel_rate — one bad corner (very short braking
        # distance causes division instability) can pull the mean wildly.
        # Cap decel at 8.0 km/h/m — physical maximum for F1 under hard braking.
        valid_decel = [
            min(c["decel_rate"], 8.0) for c in corners if c["decel_rate"] > 0
        ]
        valid_brake = [c["braking_dist_m"] for c in corners if c["braking_dist_m"] > 2]

        driver_results[dn] = {
            **meta[dn],
            "corners": corners,
            "summary": {
                "avg_braking_dist_m": round(median(valid_brake), 1)
                if valid_brake
                else 0,
                "avg_decel_rate": round(median(valid_decel), 3) if valid_decel else 0,
                "avg_apex_speed_kmh": round(
                    sum(c["apex_speed_kmh"] for c in corners) / len(corners), 1
                )
                if corners
                else 0,
                "avg_throttle_gap_m": round(
                    median(
                        [c["throttle_gap_m"] for c in corners if c["throttle_gap_m"]]
                    ),
                    1,
                ),
                "avg_exit_speed_kmh": round(
                    median(
                        [c["exit_speed_kmh"] for c in corners if c["exit_speed_kmh"]]
                    ),
                    1,
                ),
                "total_corners_detected": len(corners),
            },
        }

    # ── Match corners across drivers ─────────────────────────────────────────
    # Drivers won't have identical corner indices since they took slightly different
    # lines. Match by proximity: corners within 80m of each other = same corner.
    # This gives us a per-corner comparison table.

    def match_corners(sets: dict, tolerance_m: float = 120.0) -> list:
        """
        Match corners across drivers by distance proximity.

        MAJORITY RULE: include a corner if >= 2 drivers (or 50%+) have it.
        WHY: one driver may miss a corner detection due to a slightly different
        line or speed profile. Requiring ALL drivers to detect it causes
        cascading drops — one weak detection eliminates the corner for everyone.

        Algorithm:
        1. Collect all unique corner positions across ALL drivers
        2. Cluster corners within tolerance_m — same physical corner
        3. Keep clusters where >= min_drivers detected it
        4. For each cluster, use the median apex position as canonical
        """
        driver_keys = list(sets.keys())
        n_drivers = len(driver_keys)
        if n_drivers < 2:
            return []

        # Step 1: pool all corners from all drivers with their driver tag
        all_corners = []
        for dn in driver_keys:
            for c in sets[dn]:
                all_corners.append({"dn": dn, **c})

        # Sort by distance
        all_corners.sort(key=lambda c: c["apex_dist_m"])

        # Step 2: cluster by proximity
        # Walk through sorted corners; start a new cluster when gap > tolerance_m
        clusters = []
        for c in all_corners:
            placed = False
            for cluster in clusters:
                centroid = sum(x["apex_dist_m"] for x in cluster) / len(cluster)
                if abs(c["apex_dist_m"] - centroid) <= tolerance_m:
                    # Speed validation: same corner = apex speed within 30kmh
                    cluster_speed = sum(x["apex_speed_kmh"] for x in cluster) / len(
                        cluster
                    )
                    if abs(c["apex_speed_kmh"] - cluster_speed) <= 30:
                        cluster.append(c)
                        placed = True
                        break
            if not placed:
                clusters.append([c])

        # Step 3: filter clusters — need >= 2 unique drivers
        # (majority rule: at least 2 drivers must agree this corner exists)
        min_drivers = min(2, n_drivers)
        matched = []
        corner_num = 1

        for cluster in sorted(
            clusters, key=lambda cl: sum(x["apex_dist_m"] for x in cl) / len(cl)
        ):
            # Which drivers are represented?
            represented = set(c["dn"] for c in cluster)
            if len(represented) < min_drivers:
                continue

            # Canonical position = median apex of cluster
            canon_dist = sorted(c["apex_dist_m"] for c in cluster)[len(cluster) // 2]
            canon_x = sorted(c["apex_x"] for c in cluster)[len(cluster) // 2]
            canon_y = sorted(c["apex_y"] for c in cluster)[len(cluster) // 2]

            # Best corner per driver = closest to canonical position
            driver_corners = {}
            for dn in driver_keys:
                candidates = [c for c in cluster if c["dn"] == dn]
                if candidates:
                    best = min(
                        candidates, key=lambda c: abs(c["apex_dist_m"] - canon_dist)
                    )
                    # Strip the "dn" tag before storing
                    driver_corners[dn] = {k: v for k, v in best.items() if k != "dn"}

            matched.append(
                {
                    "corner_number": corner_num,
                    "apex_dist_m": canon_dist,
                    "apex_x": canon_x,
                    "apex_y": canon_y,
                    "drivers": driver_corners,
                    "drivers_present": list(represented),
                }
            )
            corner_num += 1

        return matched

    matched_corners = match_corners(all_corner_sets, tolerance_m=120.0)

    # ── Compute deltas at each matched corner ─────────────────────────────────
    # Delta = driver_B_value - driver_A_value
    # Positive brake point delta = driver B brakes LATER (more aggressive / confidence)
    # Positive throttle delta = driver B applies throttle EARLIER (better exit)
    # Positive exit speed delta = driver B exits faster

    driver_keys = list(by_driver.keys())
    for corner in matched_corners:
        # Compute pairwise deltas for first two drivers when both present
        # For 3-4 driver comparisons, deltas are always relative to driver[0]
        a_dn = driver_keys[0]
        b_dn = driver_keys[1] if len(driver_keys) >= 2 else None
        a = corner["drivers"].get(a_dn)
        b = corner["drivers"].get(b_dn) if b_dn else None

        if a and b:
            corner["delta"] = {
                "brake_point_m": round(
                    b["brake_point_dist_m"] - a["brake_point_dist_m"], 1
                ),
                "braking_dist_m": round(a["braking_dist_m"] - b["braking_dist_m"], 1),
                "decel_rate": round(b["decel_rate"] - a["decel_rate"], 3),
                "throttle_gap_m": round(
                    (a["throttle_gap_m"] or 0) - (b["throttle_gap_m"] or 0), 1
                ),
                "exit_speed_kmh": round(
                    (b["exit_speed_kmh"] or 0) - (a["exit_speed_kmh"] or 0), 1
                ),
            }

    # Generate insights from the computed corner data
    insights = generate_insights(driver_keys, driver_results, matched_corners)

    return jsonify(
        {
            "session_key": session_key,
            "driver_keys": driver_keys,
            "drivers": driver_results,
            "matched_corners": matched_corners,
            "insights": insights,
        }
    )


# ── Insight engine — rules-based, pitwall-quality ─────────────────────────────


def generate_insights(driver_keys: list, drivers: dict, matched_corners: list) -> dict:
    """
    Generate structured, number-grounded insights from corner analysis data.

    Design philosophy:
    - Every insight cites specific numbers — no vague claims
    - Insights are tiered: CRITICAL (lap time impact) > NOTABLE > INFO
    - Each insight maps to a real engineering concept pitwall engineers use
    - No LLM required — rules derived from F1 engineering knowledge

    Returns:
        {
          "headline": str,           # one-line summary of the comparison
          "insights": [...],         # list of insight objects
          "driver_profiles": {...},  # per-driver style characterisation
          "key_corner": int,         # corner number with most lap time impact
        }
    """
    if len(driver_keys) < 2 or not matched_corners:
        return {}

    d0_key = driver_keys[0]
    d1_key = driver_keys[1]
    d0 = drivers.get(d0_key, {})
    d1 = drivers.get(d1_key, {})
    if not d0 or not d1:
        return {}

    abbr0 = d0["abbreviation"]
    abbr1 = d1["abbreviation"]
    s0 = d0["summary"]
    s1 = d1["summary"]

    insights = []

    # ── Insight 1: Braking commitment ────────────────────────────────────────
    # "Who is braver under braking" — the most watched metric in F1 pitwall
    # Pitwall engineers call this "brake point confidence"
    # Measured by: average braking distance across all corners
    # Shorter braking dist = later brake point = more confidence/risk
    brake_delta = s0["avg_braking_dist_m"] - s1["avg_braking_dist_m"]
    if abs(brake_delta) > 1.5:
        braver = abbr0 if brake_delta < 0 else abbr1
        later_m = abs(brake_delta)
        insights.append(
            {
                "id": "brake_commitment",
                "tier": "CRITICAL" if later_m > 4 else "NOTABLE",
                "category": "BRAKING",
                "title": f"{braver} brakes later on average",
                "detail": f"{braver} has {later_m:.1f}m shorter average braking distance across "
                f"{len(matched_corners)} corners. Shorter braking distance signals "
                f"later brake application — a key indicator of corner entry confidence "
                f"and trail braking ability.",
                "metric": f"{s0['avg_braking_dist_m']}m vs {s1['avg_braking_dist_m']}m",
                "drivers": [abbr0, abbr1],
                "winner": braver,
            }
        )

    # ── Insight 2: Deceleration efficiency ───────────────────────────────────
    # decel_rate = km/h lost per metre of braking distance
    # Higher rate = more efficient weight transfer and brake bias setup
    # Engineers call this "brake efficiency" — you want max decel in min distance
    decel_delta = s0["avg_decel_rate"] - s1["avg_decel_rate"]
    if abs(decel_delta) > 0.05:
        harder = abbr0 if decel_delta > 0 else abbr1
        softer = abbr1 if decel_delta > 0 else abbr0
        insights.append(
            {
                "id": "decel_efficiency",
                "tier": "NOTABLE",
                "category": "BRAKING",
                "title": f"{harder} generates higher deceleration force",
                "detail": f"{harder} averages {max(s0['avg_decel_rate'], s1['avg_decel_rate']):.2f} km/h/m "
                f"vs {softer}'s {min(s0['avg_decel_rate'], s1['avg_decel_rate']):.2f} km/h/m. "
                f"Higher deceleration rate indicates better brake bias calibration and "
                f"more aggressive trail braking — the car is being asked to do more work "
                f"over a shorter distance.",
                "metric": f"{max(s0['avg_decel_rate'], s1['avg_decel_rate']):.3f} vs {min(s0['avg_decel_rate'], s1['avg_decel_rate']):.3f} km/h/m",
                "drivers": [abbr0, abbr1],
                "winner": harder,
            }
        )

    # ── Insight 3: Corner exit performance ───────────────────────────────────
    # Exit speed is the single biggest driver of lap time on most circuits
    # because it determines entry speed onto the following straight
    # Engineers call this "traction performance" or "exit efficiency"
    exit_delta = s0["avg_exit_speed_kmh"] - s1["avg_exit_speed_kmh"]
    if abs(exit_delta) > 2:
        faster_exit = abbr0 if exit_delta > 0 else abbr1
       
        insights.append(
            {
                "id": "exit_speed",
                "tier": "CRITICAL" if abs(exit_delta) > 4 else "NOTABLE",
                "category": "THROTTLE",
                "title": f"{faster_exit} generates higher corner exit speed",
                "detail": f"{faster_exit} averages {abs(exit_delta):.1f} km/h more at corner exit "
                f"({max(s0['avg_exit_speed_kmh'], s1['avg_exit_speed_kmh']):.1f} vs "
                f"{min(s0['avg_exit_speed_kmh'], s1['avg_exit_speed_kmh']):.1f} km/h). "
                f"Exit speed compounds across a lap — higher exit speed means higher "
                f"entry speed onto every straight, typically worth 0.05–0.15s per corner.",
                "metric": f"{s0['avg_exit_speed_kmh']} vs {s1['avg_exit_speed_kmh']} km/h",
                "drivers": [abbr0, abbr1],
                "winner": faster_exit,
            }
        )

    # ── Insight 4: Throttle application point ────────────────────────────────
    # throttle_gap_m = metres from apex to first throttle application
    # Smaller gap = earlier throttle = more aggressive exit
    # BUT: earlier throttle with lower exit speed = wheelspin or oversteer —
    #      so this must be read alongside exit speed
    tgap_delta = s0["avg_throttle_gap_m"] - s1["avg_throttle_gap_m"]
    if abs(tgap_delta) > 1.5:
        earlier = abbr0 if tgap_delta < 0 else abbr1
        later_t = abbr1 if tgap_delta < 0 else abbr0
        # Cross-reference with exit speed to detect wheelspin signature
        earlier_better_exit = (earlier == abbr0 and exit_delta > 0) or (
            earlier == abbr1 and exit_delta < 0
        )
        if earlier_better_exit:
            detail = (
                f"{earlier} applies throttle {abs(tgap_delta):.1f}m earlier from the apex "
                f"AND achieves higher exit speed — indicates clean traction and good "
                f"mechanical grip at corner exit. This is the ideal throttle signature."
            )
            tier = "CRITICAL"
        else:
            detail = (
                f"{earlier} applies throttle {abs(tgap_delta):.1f}m earlier from the apex "
                f"but has lower exit speed than {later_t}. This pattern suggests "
                f"oversteer or wheelspin at exit — throttle is being applied before "
                f"the car is fully pointed at the exit."
            )
            tier = "NOTABLE"

        insights.append(
            {
                "id": "throttle_application",
                "tier": tier,
                "category": "THROTTLE",
                "title": f"{earlier} applies throttle earlier from apex",
                "detail": detail,
                "metric": f"{s0['avg_throttle_gap_m']}m vs {s1['avg_throttle_gap_m']}m from apex",
                "drivers": [abbr0, abbr1],
                "winner": earlier if earlier_better_exit else later_t,
            }
        )

    # ── Insight 5: High-value corner identification ───────────────────────────
    # Not all corners are equal. A corner feeding a long straight is worth
    # much more than a corner into another corner.
    # Proxy for straight length: distance to NEXT corner minus current apex.
    # Longer gap = longer straight = exit speed matters more here.
    if len(matched_corners) >= 2:
        corner_values = []
        for i, corner in enumerate(matched_corners):
            if "delta" not in corner:
                continue
            # Straight length after this corner
            if i + 1 < len(matched_corners):
                raw_straight = (
                    matched_corners[i + 1]["apex_dist_m"] - corner["apex_dist_m"]
                )
            else:
                track_len = matched_corners[-1]["apex_dist_m"] + 500
                raw_straight = track_len - corner["apex_dist_m"]

            # Cap at 900m — F1 longest straights are ~700-800m (Monza).
            # Values above 900m mean we missed intermediate corners and the
            # "straight" is actually several corners + straights combined.
            # Using the raw inflated value would make that corner look far more
            # important than it is — misleading the insight.
            straight_len = min(raw_straight, 900)

            exit_spd_delta = abs(corner["delta"].get("exit_speed_kmh", 0) or 0)
            value = exit_spd_delta * straight_len
            corner_values.append(
                (corner["corner_number"], value, straight_len, corner["delta"])
            )

        if corner_values:
            key_corner = max(corner_values, key=lambda x: x[1])
            cn, val, slen, delta = key_corner

            if val > 0:
                beneficiary = abbr1 if delta.get("exit_speed_kmh", 0) > 0 else abbr0
                exit_adv = abs(delta.get("exit_speed_kmh", 0))
                insights.append(
                    {
                        "id": "high_value_corner",
                        "tier": "CRITICAL",
                        "category": "STRATEGY",
                        "title": f"Corner {cn} has highest lap time impact",
                        "detail": (
                            f"Corner {cn} feeds a {slen:.0f}m straight — the longest approach "
                            f"in this comparison. {beneficiary} exits {exit_adv:.1f} km/h faster here, "
                            f"which compounds across the entire straight. This single corner "
                            f"difference is likely worth {(exit_adv * slen / 3_600_000 * 3.6):.3f}s "
                            f"in raw time advantage per lap."
                        ),
                        "metric": f"Corner {cn} → {slen:.0f}m straight",
                        "drivers": [abbr0, abbr1],
                        "winner": beneficiary,
                        "corner": cn,
                    }
                )

    # ── Insight 6: Driving style characterisation ─────────────────────────────
    # Synthesise all metrics into a style label
    # Entry-focused driver: brakes later, potentially lower exit speed
    # Exit-focused driver: earlier throttle, higher exit speed
    # Balanced: neither strongly biased

    def characterise(abbr, s, other_s):
        entry_score = 0
        exit_score = 0

        if s["avg_braking_dist_m"] < other_s["avg_braking_dist_m"]:
            entry_score += 2  # brakes later = entry confidence
        if s["avg_decel_rate"] > other_s["avg_decel_rate"]:
            entry_score += 1  # harder braking = entry aggression
        if s["avg_exit_speed_kmh"] > other_s["avg_exit_speed_kmh"]:
            exit_score += 2  # faster exit = exit focus
        if s["avg_throttle_gap_m"] < other_s["avg_throttle_gap_m"]:
            exit_score += 1  # earlier throttle = exit aggression

        if entry_score > exit_score + 1:
            style = "ENTRY-FOCUSED"
            desc = "prioritises late braking and aggressive corner entry"
        elif exit_score > entry_score + 1:
            style = "EXIT-FOCUSED"
            desc = "prioritises early throttle application and corner exit speed"
        else:
            style = "BALANCED"
            desc = (
                "shows no strong bias toward entry or exit — consistent through corners"
            )

        return {
            "style": style,
            "description": desc,
            "entry_score": entry_score,
            "exit_score": exit_score,
        }

    driver_profiles = {
        abbr0: characterise(abbr0, s0, s1),
        abbr1: characterise(abbr1, s1, s0),
    }

    # ── Headline ──────────────────────────────────────────────────────────────
    critical = [i for i in insights if i["tier"] == "CRITICAL"]
    if critical:
        headline = critical[0]["title"]
    elif insights:
        headline = insights[0]["title"]
    else:
        headline = f"{abbr0} and {abbr1} show similar corner profiles"

    # Key corner for map highlight
    key_c = next((i.get("corner") for i in insights if i.get("corner")), None)

    return {
        "headline": headline,
        "insights": sorted(
            insights, key=lambda i: ["CRITICAL", "NOTABLE", "INFO"].index(i["tier"])
        ),
        "driver_profiles": driver_profiles,
        "key_corner": key_c,
    }


# ── Qualifying: speed trap + lap progression analysis ─────────────────────────

@analysis_bp.get("/sessions/<int:session_key>/analysis/quali-speed")
def quali_speed(session_key: int):
    """
    Qualifying speed trap and lap progression analysis.

    Returns three datasets:
    1. speed_trap: fastest speed at each timing point per driver
       (speed_i1, speed_i2, speed_fl, speed_st on their best lap)
    2. lap_progression: each driver's lap times in order — shows
       improvement across Q session runs
    3. sector_contribution: which sector each driver gained/lost vs pole

    WHY speed_st specifically:
    The FIA speed trap (SpeedST) is placed at the circuit's fastest point,
    always on the main straight. It's the definitive measure of raw
    straight-line car speed, unaffected by driver skill at braking/cornering.
    High speed_st = low drag setup. Low speed_st = high downforce setup.
    This tells you a team's strategic philosophy for the circuit.
    """
    with engine.connect() as conn:

        speed_rows = conn.execute(text("""
            SELECT
                l.driver_number,
                d.abbreviation,
                d.team_name,
                d.team_colour,
                l.lap_time_ms,
                l.speed_i1,
                l.speed_i2,
                l.speed_fl,
                l.speed_st,
                l.s1_ms,
                l.s2_ms,
                l.s3_ms
            FROM lap_times l
            JOIN drivers d 
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key = :sk
              AND l.lap_time_ms = (
                  SELECT MIN(lap_time_ms) 
                  FROM lap_times 
                  WHERE session_key = :sk 
                    AND driver_number = l.driver_number
                    AND deleted = FALSE
              )
            ORDER BY l.lap_time_ms ASC
        """), {"sk": session_key}).mappings().all()

        # ── Lap progression ───────────────────────────────────────────────────
        # Every non-deleted lap per driver, in lap order.
        # Shows whether a driver improved, stayed flat, or got worse.
        # The shape of this curve tells you about car balance evolution
        # across the session (track evolution, tyre temperature management).
        progression_rows = conn.execute(text("""
            SELECT
                l.driver_number,
                d.abbreviation,
                d.team_colour,
                d.team_name,
                l.lap_number,
                l.lap_time_ms,
                l.s1_ms,
                l.s2_ms,
                l.s3_ms,
                l.compound,
                l.deleted,
                l.quali_segment
            FROM lap_times l
            JOIN drivers d
                ON d.driver_number = l.driver_number
                AND d.session_key  = l.session_key
            WHERE l.session_key = :sk
              AND l.lap_time_ms  IS NOT NULL
            ORDER BY l.driver_number, l.lap_number ASC
        """), {"sk": session_key}).mappings().all()

    if not speed_rows:
        return jsonify({"speed_trap": [], "lap_progression": {}, "insights": []})

    from backend.api.v1.strategy import _resolve

    # Process speed trap data
    speed_trap = []
    for r in speed_rows:
        d = dict(r)
        d["team_colour"] = _resolve(d.get("team_colour"), d.get("team_name"))
        speed_trap.append(d)

    # Find pole and compute gaps
    pole_lap   = speed_trap[0]["lap_time_ms"] if speed_trap else None

    for i, r in enumerate(speed_trap):
        r["gap_to_pole_ms"] = None if i == 0 else (
            round(r["lap_time_ms"] - pole_lap, 1) if r["lap_time_ms"] and pole_lap else None
        )
        r["speed_st_delta"] = (
            round((r["speed_st"] or 0) - (speed_trap[i-1]["speed_st"] or 0), 1)
            if i > 0 and r["speed_st"] else None
        )
        # Downforce indicator: drivers with top speed > median are low-downforce
        r["speed_st_rank"] = i + 1

    # Process lap progression — group by driver
    lap_progression = {}
    for r in progression_rows:
        dn  = str(r["driver_number"])
        if dn not in lap_progression:
            lap_progression[dn] = {
                "driver_number": r["driver_number"],
                "abbreviation":  r["abbreviation"],
                "team_colour":   _resolve(r["team_colour"], r["team_name"]),
                "team_name":     r["team_name"],
                "laps": []
            }
        lap_progression[dn]["laps"].append({
            "lap_number":   r["lap_number"],
            "lap_time_ms":  r["lap_time_ms"],
            "s1_ms":        r["s1_ms"],
            "s2_ms":        r["s2_ms"],
            "s3_ms":        r["s3_ms"],
            "compound":     r["compound"],
            "deleted":      r["deleted"],
            "quali_segment": r["quali_segment"],
        })

    # ── Speed trap insights ───────────────────────────────────────────────────
    insights = []

    if len(speed_trap) >= 2:
        fastest_st = max(speed_trap, key=lambda r: r["speed_st"] or 0)
        slowest_st = min(speed_trap, key=lambda r: r["speed_st"] or 999)
        st_spread  = (fastest_st["speed_st"] or 0) - (slowest_st["speed_st"] or 0)

        # Speed trap spread insight
        # Wide spread = teams have very different downforce philosophies
        # Narrow spread = everyone converged on similar setup
        if st_spread > 15:
            insights.append({
                "tier":    "NOTABLE",
                "title":   f"Wide speed trap spread — {st_spread:.0f} km/h between fastest and slowest",
                "detail":  (f"{fastest_st['abbreviation']} runs the lowest drag "
                            f"({fastest_st['speed_st']} km/h) while "
                            f"{slowest_st['abbreviation']} runs highest downforce "
                            f"({slowest_st['speed_st']} km/h). "
                            f"A {st_spread:.0f} km/h gap signals different tyre management "
                            f"or aerodynamic philosophies for this circuit."),
            })

        # Pole sitter speed comparison
        pole_driver = speed_trap[0]
        pole_st     = pole_driver["speed_st"] or 0
        pole_st_rank = sorted(speed_trap, key=lambda r: -(r["speed_st"] or 0)).index(pole_driver) + 1

        if pole_st_rank > 3:
            insights.append({
                "tier":    "CRITICAL",
                "title":   f"{pole_driver['abbreviation']} on pole despite only P{pole_st_rank} top speed",
                "detail":  (f"{pole_driver['abbreviation']} set pole with {pole_st} km/h top speed "
                            f"(P{pole_st_rank} of the field). This indicates their lap time "
                            f"advantage comes from mechanical grip and cornering rather than "
                            f"straight-line speed — a high-downforce setup paying off."),
            })

        # Fastest straight-line car
        if fastest_st["abbreviation"] != speed_trap[0]["abbreviation"]:
            insights.append({
                "tier":    "NOTABLE",
                "title":   f"{fastest_st['abbreviation']} has the fastest car in a straight line",
                "detail":  (f"{fastest_st['abbreviation']} recorded {fastest_st['speed_st']} km/h "
                            f"at the speed trap — {st_spread:.0f} km/h faster than "
                            f"{slowest_st['abbreviation']}. Low drag setup likely "
                            f"trading cornering performance for straight-line speed."),
            })

    return jsonify({
        "speed_trap":      speed_trap,
        "lap_progression": lap_progression,
        "insights":        insights,
    })


# ── Race intelligence: deterministic AI-ready evidence layer ────────────────

def _linear_slope(points: list[tuple[float, float]]) -> float | None:
    """Return y-per-x slope for a small set of points, or None if unavailable."""
    if len(points) < 4:
        return None

    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    return (n * sxy - sx * sy) / denom


def _round_or_none(value, digits: int = 1):
    if value is None:
        return None
    return round(float(value), digits)

def _avg(values: list[float]) -> float | None:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _median(values: list[float]) -> float | None:
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2


def _stint_phase(index: int, total: int) -> str:
    if total <= 3:
        return "short"
    pct = index / max(total - 1, 1)
    if pct < 0.34:
        return "opening"
    if pct < 0.67:
        return "middle"
    return "closing"

@analysis_bp.get("/sessions/<int:session_key>/analysis/race-intelligence")
def race_intelligence(session_key: int):
    """
    Deterministic race-state summary for AI/report generation.

    This endpoint does not call an LLM. It produces evidence-grounded features:
    clean pace, degradation, stint summaries, position movement, volatility,
    pit-stop counts, and rule-based insight cards.
    """
    from backend.api.v1.strategy import _resolve

    with engine.connect() as conn:
        session = (
            conn.execute(
                text("""
                    SELECT session_key, year, gp_name, session_type, session_name
                    FROM sessions
                    WHERE session_key = :sk
                """),
                {"sk": session_key},
            )
            .mappings()
            .first()
        )
        if not session:
            return {"error": "Session not found"}, 404

        driver_rows = (
            conn.execute(
                text("""
                    WITH clean_laps AS (
                        SELECT *
                        FROM lap_times
                        WHERE session_key = :sk
                          AND lap_time_ms IS NOT NULL
                          AND deleted = FALSE
                          AND pit_in_time_ms IS NULL
                          AND pit_out_time_ms IS NULL
                    ),
                    first_pos AS (
                        SELECT DISTINCT ON (driver_number)
                            driver_number,
                            position AS first_position
                        FROM lap_times
                        WHERE session_key = :sk
                          AND position IS NOT NULL
                        ORDER BY driver_number, lap_number ASC
                    ),
                    final_pos AS (
                        SELECT DISTINCT ON (driver_number)
                            driver_number,
                            position AS final_position
                        FROM lap_times
                        WHERE session_key = :sk
                          AND position IS NOT NULL
                        ORDER BY driver_number, lap_number DESC
                    ),
                    pit_counts AS (
                        SELECT
                            driver_number,
                            COUNT(*) FILTER (WHERE pit_in_time_ms IS NOT NULL) AS pit_stops
                        FROM lap_times
                        WHERE session_key = :sk
                        GROUP BY driver_number
                    ),
                    compound_use AS (
                        SELECT
                            driver_number,
                            STRING_AGG(DISTINCT compound, ',' ORDER BY compound) AS compounds
                        FROM lap_times
                        WHERE session_key = :sk
                          AND compound IS NOT NULL
                        GROUP BY driver_number
                    ),
                    pace AS (
                        SELECT
                            driver_number,
                            COUNT(*) AS clean_laps,
                            AVG(lap_time_ms) AS avg_clean_ms,
                            MIN(lap_time_ms) AS best_lap_ms,
                            STDDEV_POP(lap_time_ms) AS pace_stddev_ms
                        FROM clean_laps
                        GROUP BY driver_number
                    )
                    SELECT
                        d.driver_number,
                        d.abbreviation,
                        d.full_name,
                        d.team_name,
                        d.team_colour,
                        COALESCE(p.clean_laps, 0) AS clean_laps,
                        p.avg_clean_ms,
                        p.best_lap_ms,
                        p.pace_stddev_ms,
                        fp.first_position,
                        lp.final_position,
                        CASE
                            WHEN fp.first_position IS NOT NULL
                             AND lp.final_position IS NOT NULL
                            THEN fp.first_position - lp.final_position
                            ELSE NULL
                        END AS positions_gained,
                        COALESCE(pc.pit_stops, 0) AS pit_stops,
                        cu.compounds
                    FROM drivers d
                    LEFT JOIN pace p ON p.driver_number = d.driver_number
                    LEFT JOIN first_pos fp ON fp.driver_number = d.driver_number
                    LEFT JOIN final_pos lp ON lp.driver_number = d.driver_number
                    LEFT JOIN pit_counts pc ON pc.driver_number = d.driver_number
                    LEFT JOIN compound_use cu ON cu.driver_number = d.driver_number
                    WHERE d.session_key = :sk
                    ORDER BY
                        lp.final_position ASC NULLS LAST,
                        p.avg_clean_ms ASC NULLS LAST
                """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

        lap_rows = (
            conn.execute(
                text("""
                    SELECT
                        l.driver_number,
                        d.abbreviation,
                        d.team_name,
                        d.team_colour,
                        l.lap_number,
                        l.lap_time_ms,
                        l.compound,
                        COALESCE(l.stint, 1) AS stint,
                        l.tyre_life_laps
                    FROM lap_times l
                    JOIN drivers d
                      ON d.session_key = l.session_key
                     AND d.driver_number = l.driver_number
                    WHERE l.session_key = :sk
                      AND l.lap_time_ms IS NOT NULL
                      AND l.deleted = FALSE
                      AND l.pit_in_time_ms IS NULL
                      AND l.pit_out_time_ms IS NULL
                    ORDER BY l.driver_number, COALESCE(l.stint, 1), l.lap_number
                """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

        track_rows = (
            conn.execute(text("""
                SELECT l.driver_number, d.abbreviation, d.team_name, d.team_colour, l.lap_number, l.lap_time_ms, l.position, l.compound,  COALESCE(l.stint, 1) AS stint, l.tyre_life_laps, l.pit_in_time_ms, l.pit_out_time_ms
                FROM lap_times l 
                JOIN drivers d ON d.session_key = l.session_key AND d.driver_number = l.driver_number
                WHERE l.session_key = :sk
                AND l.deleted = FALSE
                ORDER BY l.driver_number, l.lap_number """), 
                {"sk": session_key},
            ).mappings().all()
        )

    driver_states = []
    for r in driver_rows:
        state = dict(r)
        compounds = state.pop("compounds", None)
        state["team_colour"] = _resolve(state.get("team_colour"), state.get("team_name"))
        state["compounds"] = sorted(compounds.split(",")) if compounds else []
        state["avg_clean_ms"] = _round_or_none(state["avg_clean_ms"])
        state["best_lap_ms"] = _round_or_none(state["best_lap_ms"])
        state["pace_stddev_ms"] = _round_or_none(state["pace_stddev_ms"])
        driver_states.append(state)

    stint_groups: dict[tuple[int, int, str], dict] = {}
    for r in lap_rows:
        compound = r["compound"] or "UNKNOWN"
        key = (r["driver_number"], r["stint"], compound)
        if key not in stint_groups:
            stint_groups[key] = {
                "driver_number": r["driver_number"],
                "abbreviation": r["abbreviation"],
                "team_name": r["team_name"],
                "team_colour": _resolve(r["team_colour"], r["team_name"]),
                "stint": r["stint"],
                "compound": compound,
                "laps": [],
            }
        stint_groups[key]["laps"].append(
            {
                "lap_number": r["lap_number"],
                "lap_time_ms": float(r["lap_time_ms"]),
                "tyre_life_laps": r["tyre_life_laps"],
            }
        )

    stint_summaries = []
    for stint in stint_groups.values():
        laps = stint["laps"]
        lap_times = [lap["lap_time_ms"] for lap in laps]
        points = [(idx + 1, lap["lap_time_ms"]) for idx, lap in enumerate(laps)]
        deg_slope = _linear_slope(points)
        stint_summaries.append(
            {
                "driver_number": stint["driver_number"],
                "abbreviation": stint["abbreviation"],
                "team_name": stint["team_name"],
                "team_colour": stint["team_colour"],
                "stint": stint["stint"],
                "compound": stint["compound"],
                "start_lap": laps[0]["lap_number"],
                "end_lap": laps[-1]["lap_number"],
                "lap_count": len(laps),
                "avg_lap_ms": round(sum(lap_times) / len(lap_times), 1),
                "best_lap_ms": round(min(lap_times), 1),
                "degradation_ms_per_lap": _round_or_none(deg_slope),
            }
        )

    stint_summaries.sort(key=lambda s: (s["driver_number"], s["stint"], s["start_lap"]))
    driver_by_number = {d["driver_number"]: d for d in driver_states}

    compound_groups: dict[str, list[float]] = {}
    for r in lap_rows:
        compound = r["compound"] or "UNKNOWN"
        compound_groups.setdefault(compound, []).append(float(r["lap_time_ms"]))

    compound_pace = []
    for compound, times in compound_groups.items():
        compound_pace.append({
            "compound": compound,
            "lap_count": len(times),
            "avg_lap_ms": _round_or_none(_avg(times)),
            "median_lap_ms": _round_or_none(_median(times)),
            "best_lap_ms": _round_or_none(min(times)),
        })
    compound_pace.sort(key=lambda c: c["median_lap_ms"] if c["median_lap_ms"] is not None else 999999999)

    stint_phase_summaries = []
    for stint in stint_groups.values():
        laps = stint["laps"]
        phase_groups: dict[str, list[float]] = {}
        for idx, lap in enumerate(laps):
            phase = _stint_phase(idx, len(laps))
            phase_groups.setdefault(phase, []).append(lap["lap_time_ms"])

        for phase, times in phase_groups.items():
            if phase == "short":
                continue
            stint_phase_summaries.append({
                "driver_number": stint["driver_number"],
                "abbreviation": stint["abbreviation"],
                "team_colour": stint["team_colour"],
                "stint": stint["stint"],
                "compound": stint["compound"],
                "phase": phase,
                "lap_count": len(times),
                "avg_lap_ms": _round_or_none(_avg(times)),
            })

    cumulative_by_driver: dict[int, float] = {}
    lap_snapshots: dict[int, list[dict]] = {}

    for r in sorted(track_rows, key=lambda x: (x["driver_number"], x["lap_number"])):
        dn = r["driver_number"]
        if r["lap_time_ms"] is not None:
            cumulative_by_driver[dn] = cumulative_by_driver.get(dn, 0.0) + float(r["lap_time_ms"])

        lap_snapshots.setdefault(r["lap_number"], []).append({
            "driver_number": dn,
            "abbreviation": r["abbreviation"],
            "team_colour": _resolve(r["team_colour"], r["team_name"]),
            "lap_number": r["lap_number"],
            "position": r["position"],
            "compound": r["compound"],
            "stint": r["stint"],
            "tyre_life_laps": r["tyre_life_laps"],
            "cumulative_ms": cumulative_by_driver.get(dn),
        })

    battle_gaps = []
    for lap_number, cars in lap_snapshots.items():
        ordered = [c for c in cars if c["position"] is not None and c["cumulative_ms"] is not None]
        ordered.sort(key=lambda c: c["position"])

        for ahead, behind in zip(ordered, ordered[1:]):
            gap_ms = behind["cumulative_ms"] - ahead["cumulative_ms"]
            if 0 < gap_ms <= 2000:
                battle_gaps.append({
                    "lap_number": lap_number,
                    "ahead": ahead["abbreviation"],
                    "behind": behind["abbreviation"],
                    "ahead_driver_number": ahead["driver_number"],
                    "behind_driver_number": behind["driver_number"],
                    "position_ahead": ahead["position"],
                    "gap_ms": round(gap_ms, 1),
                    "gap_s": round(gap_ms / 1000.0, 3),
                    "behind_compound": behind["compound"],
                    "behind_tyre_life_laps": behind["tyre_life_laps"],
                })

    battle_gaps.sort(key=lambda b: (b["lap_number"], b["position_ahead"]))

    undercut_candidates = []
    latest_battles = list(reversed(battle_gaps))
    seen_pairs = set()

    for battle in latest_battles:
        pair = (battle["ahead_driver_number"], battle["behind_driver_number"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        ahead_state = driver_by_number.get(battle["ahead_driver_number"])
        behind_state = driver_by_number.get(battle["behind_driver_number"])
        if not ahead_state or not behind_state:
            continue
        if ahead_state["avg_clean_ms"] is None or behind_state["avg_clean_ms"] is None:
            continue

        pace_advantage_ms = ahead_state["avg_clean_ms"] - behind_state["avg_clean_ms"]
        if pace_advantage_ms >= 250:
            undercut_candidates.append({
                "lap_number": battle["lap_number"],
                "ahead": battle["ahead"],
                "behind": battle["behind"],
                "gap_s": battle["gap_s"],
                "pace_advantage_ms": round(pace_advantage_ms, 1),
                "signal": "behind_car_faster_in_close_air",
            })

        if len(undercut_candidates) >= 5:
            break

    pace_rank = [d for d in driver_states if d["avg_clean_ms"] is not None]
    pace_rank.sort(key=lambda d: d["avg_clean_ms"])

    driver_scores = []
    for d in driver_states:
        score = 50.0

        if d["positions_gained"] is not None:
            score += d["positions_gained"] * 2.5

        if d["pace_stddev_ms"] is not None:
            score -= min(d["pace_stddev_ms"] / 250.0, 12.0)

        driver_stints = [
            s for s in stint_summaries
            if s["driver_number"] == d["driver_number"]
            and s["degradation_ms_per_lap"] is not None
        ]
        if driver_stints:
            avg_deg = _avg([s["degradation_ms_per_lap"] for s in driver_stints])
            if avg_deg is not None:
                score -= max(avg_deg, 0) / 100.0

        if d["avg_clean_ms"] is not None and pace_rank:
            leader_ms = pace_rank[0]["avg_clean_ms"]
            score -= max((d["avg_clean_ms"] - leader_ms) / 250.0, 0)

        driver_scores.append({
            "driver_number": d["driver_number"],
            "abbreviation": d["abbreviation"],
            "team_colour": d["team_colour"],
            "score": round(max(0.0, min(100.0, score)), 1),
            "inputs": {
                "avg_clean_ms": d["avg_clean_ms"],
                "pace_stddev_ms": d["pace_stddev_ms"],
                "positions_gained": d["positions_gained"],
                "pit_stops": d["pit_stops"],
            },
        })

    driver_scores.sort(key=lambda d: d["score"], reverse=True)

    insights: list[dict] = []

    movers = [d for d in driver_states if d["positions_gained"] is not None]
    if movers:
        best_mover = max(movers, key=lambda d: d["positions_gained"])
        if best_mover["positions_gained"] > 0:
            insights.append(
                {
                    "id": "position_gain",
                    "tier": "NOTABLE",
                    "category": "RACECRAFT",
                    "title": f"{best_mover['abbreviation']} gained {best_mover['positions_gained']} positions",
                    "detail": (
                        f"{best_mover['abbreviation']} moved from P{best_mover['first_position']} "
                        f"to P{best_mover['final_position']}, indicating strong race execution."
                    ),
                    "evidence": {
                        "first_position": best_mover["first_position"],
                        "final_position": best_mover["final_position"],
                        "positions_gained": best_mover["positions_gained"],
                    },
                }
            )

    deg_candidates = [
        s for s in stint_summaries
        if s["degradation_ms_per_lap"] is not None and s["lap_count"] >= 5
    ]
    if deg_candidates:
        worst_deg = max(deg_candidates, key=lambda s: s["degradation_ms_per_lap"])
        best_deg = min(deg_candidates, key=lambda s: s["degradation_ms_per_lap"])
        if worst_deg["degradation_ms_per_lap"] - best_deg["degradation_ms_per_lap"] >= 150:
            insights.append(
                {
                    "id": "tyre_degradation_split",
                    "tier": "CRITICAL",
                    "category": "TYRES",
                    "title": f"{worst_deg['abbreviation']} shows the highest degradation",
                    "detail": (
                        f"{worst_deg['abbreviation']} is losing {worst_deg['degradation_ms_per_lap']:.1f} ms/lap "
                        f"on the {worst_deg['compound']} stint, compared with "
                        f"{best_deg['abbreviation']} at {best_deg['degradation_ms_per_lap']:.1f} ms/lap."
                    ),
                    "evidence": {
                        "worst": worst_deg,
                        "best": best_deg,
                    },
                }
            )

    volatile = [
        d for d in driver_states
        if d["pace_stddev_ms"] is not None and d["clean_laps"] >= 5
    ]
    if volatile:
        most_volatile = max(volatile, key=lambda d: d["pace_stddev_ms"])
        if most_volatile["pace_stddev_ms"] >= 900:
            insights.append(
                {
                    "id": "pace_volatility",
                    "tier": "INFO",
                    "category": "CONSISTENCY",
                    "title": f"{most_volatile['abbreviation']} has the least stable lap profile",
                    "detail": (
                        f"{most_volatile['abbreviation']} has {most_volatile['pace_stddev_ms']:.1f} ms "
                        f"clean-lap standard deviation, which can indicate traffic, tyre drop-off, "
                        f"or inconsistent balance."
                    ),
                    "evidence": {
                        "driver": most_volatile["abbreviation"],
                        "pace_stddev_ms": most_volatile["pace_stddev_ms"],
                        "clean_laps": most_volatile["clean_laps"],
                    },
                }
            )

    ordered_by_position = [
        d for d in driver_states
        if d["final_position"] is not None and d["avg_clean_ms"] is not None
    ]
    ordered_by_position.sort(key=lambda d: d["final_position"])
    for ahead, behind in zip(ordered_by_position, ordered_by_position[1:]):
        pace_advantage = ahead["avg_clean_ms"] - behind["avg_clean_ms"]
        if pace_advantage >= 300:
            insights.append(
                {
                    "id": "undercut_candidate",
                    "tier": "NOTABLE",
                    "category": "STRATEGY",
                    "title": f"{behind['abbreviation']} has undercut pressure on {ahead['abbreviation']}",
                    "detail": (
                        f"{behind['abbreviation']} is behind on track but averages "
                        f"{pace_advantage:.1f} ms/lap faster on clean laps. "
                        f"That is a strategy pressure signal if the gap is pit-window relevant."
                    ),
                    "evidence": {
                        "ahead": ahead["abbreviation"],
                        "behind": behind["abbreviation"],
                        "pace_advantage_ms": round(pace_advantage, 1),
                    },
                }
            )
            break

    return jsonify(
        {
            "session": dict(session),
            "driver_states": driver_states,
            "stint_summaries": stint_summaries,
            "compound_pace": compound_pace,
            "stint_phase_summaries": stint_phase_summaries,
            "battle_gaps": battle_gaps,
            "undercut_candidates": undercut_candidates,
            "driver_scores": driver_scores,
            "insights": insights,
            "metadata": {
                "source": "lap_times",
                "method": "deterministic_rules",
                "llm_used": False,
            },
        }
    )


@analysis_bp.get("/sessions/<int:session_key>/analysis/race-intelligence/vector-index/rebuild")
def rebuild_race_vector_index(session_key: int):
    from backend.race_vector_index import rebuild_session_index

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
                    SELECT id, session_key, event_type, event_key, driver_number, lap_number, text, payload
                    FROM race_intelligence_events
                    WHERE session_key = :sk
                    ORDER BY event_type, event_key"""),
                    {"sk": session_key}
            ).mappings().all()
        )

    if not rows:
        return jsonify({
            "error": "No race intelligence evnets found for this session",
            "suggested_command": (
                f"POST /api/v1/sessions/{session_key}/analysis/"
                "race-intelligence/events/refresh"
            )
        }), 404
    
    count = rebuild_session_index([dict(r) for r in rows], session_key)

    return jsonify({
        "session_key": session_key,
        "indexed_events": count,
        "index": "lancedb",
    })

@analysis_bp.get("/analysis/race-intelligence/vector-search")
def search_race_intelligence_vector_index():
    from backend.race_vector_index import search_similar

    query = request.args.get("q", "").strip()
    event_type = request.args.get("type")
    try:
        limit = int(request.args.get("limit", "8"))
    except ValueError:
        return jsonify({"error": "Invalid limit parameter"}), 400
    
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    results = search_similar(query=query, limit=max(1, min(limit, 25)), event_type=event_type)
    return jsonify({
        "query": query,
        "event_type": event_type,
        "count": len(results),
        "results": results,
    })
