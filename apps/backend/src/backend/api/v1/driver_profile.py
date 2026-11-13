"""
Driver profile API.

GET /api/v1/drivers/<code>/profile

Career totals and recent results come from ``historical_results`` (Jolpica),
identity from the newest ``drivers`` row, and style features/archetype from
``driver_features`` / ``driver_embeddings``. Every block is optional so a
driver missing from one source still returns a usable profile.
"""

from flask import Blueprint, jsonify
from sqlalchemy import text

from backend import extensions

driver_profile_bp = Blueprint("driver_profile", __name__)

# Radar axes; the *_LOWER_IS_BETTER* ones are inverted so outward is always good.
_RADAR_COLS = (
    "braking_aggression",
    "drs_usage_pct",
    "max_speed_capability",
    "lap_time_consistency",
    "avg_positions_gained",
    "podium_rate",
    "dnf_rate",
)
_LOWER_IS_BETTER = frozenset({"lap_time_consistency", "dnf_rate"})

_STYLE_COLS = (
    "braking_aggression",
    "drs_usage_pct",
    "max_speed_capability",
    "avg_speed_trap",
    "lap_time_consistency",
    "avg_positions_gained",
    "podium_rate",
    "dnf_rate",
    "quali_to_race_delta",
    "wet_pace_delta",
)




@driver_profile_bp.get("/drivers/<code>/profile")
def driver_profile(code: str):
    code = code.strip().upper()
    if not (2 <= len(code) <= 4 and code.isalpha()):
        return {"error": "Driver code must be 2-4 letters"}, 400

    with extensions.engine.connect() as conn:
        identity = (
            conn.execute(
                text("""
                    SELECT d.driver_number, d.full_name, d.abbreviation,
                           d.team_name, d.team_colour, d.headshot_url
                    FROM drivers d
                    JOIN sessions s USING (session_key)
                    WHERE UPPER(d.abbreviation) = :code
                    ORDER BY s.date_start DESC NULLS LAST
                    LIMIT 1
                """),
                {"code": code},
            )
            .mappings()
            .first()
        )

        career = (
            conn.execute(
                text("""
                    SELECT
                        COUNT(*)                                     AS grands_prix,
                        COUNT(*) FILTER (WHERE position = 1)         AS wins,
                        COUNT(*) FILTER (WHERE position <= 3)        AS podiums,
                        COUNT(*) FILTER (WHERE grid = 1)             AS poles,
                        COALESCE(SUM(points), 0)                     AS career_points,
                        COUNT(DISTINCT year)                         AS seasons,
                        MIN(year)                                    AS first_season,
                        MAX(year)                                    AS last_season
                    FROM historical_results
                    WHERE kind = 'R' AND UPPER(driver_code) = :code
                """),
                {"code": code},
            )
            .mappings()
            .first()
        )

        recent = (
            conn.execute(
                text("""
                    SELECT year, round, race_name, race_date, constructor_name,
                           grid, position, position_text, points, status
                    FROM historical_results
                    WHERE kind = 'R' AND UPPER(driver_code) = :code
                    ORDER BY race_date DESC NULLS LAST, year DESC, round DESC
                    LIMIT 5
                """),
                {"code": code},
            )
            .mappings()
            .all()
        )

        style = (
            conn.execute(
                text(
                    f"""
                    SELECT f.season, {", ".join("f." + c for c in _STYLE_COLS)},
                           e.archetype
                    FROM driver_features f
                    LEFT JOIN driver_embeddings e
                        ON e.driver_number = f.driver_number
                       AND e.season = f.season
                    WHERE UPPER(f.abbreviation) = :code
                    ORDER BY f.season DESC
                    LIMIT 1
                    """
                ),
                {"code": code},
            )
            .mappings()
            .first()
        )

        seasons = (
            conn.execute(
                text("""
                    SELECT year,
                           COUNT(*)                              AS races,
                           COUNT(*) FILTER (WHERE position = 1)  AS wins,
                           COUNT(*) FILTER (WHERE position <= 3) AS podiums,
                           COALESCE(SUM(points), 0)              AS points,
                           AVG(position)::float                  AS avg_finish,
                           AVG(grid) FILTER (WHERE grid > 0)::float AS avg_grid,
                           MODE() WITHIN GROUP (ORDER BY constructor_name) AS team
                    FROM historical_results
                    WHERE kind = 'R' AND UPPER(driver_code) = :code
                    GROUP BY year
                    ORDER BY year
                """),
                {"code": code},
            )
            .mappings()
            .all()
        )

        grid = (
            conn.execute(
                text("""
                    SELECT year, round, race_name, grid, position, points, status
                    FROM historical_results
                    WHERE kind = 'R' AND UPPER(driver_code) = :code
                    ORDER BY year, round
                """),
                {"code": code},
            )
            .mappings()
            .all()
        )

        # Per-season percentile of each style feature against the whole grid
        # (0 = worst, 1 = best), so radar axes are comparable.
        pct_cols = ", ".join(
            f"PERCENT_RANK() OVER (PARTITION BY season ORDER BY {c}"
            f"{' DESC NULLS LAST' if c in _LOWER_IS_BETTER else ' NULLS FIRST'}) AS {c}"
            for c in _RADAR_COLS
        )
        style_history = (
            conn.execute(
                text(
                    f"""
                    SELECT * FROM (
                        SELECT season, UPPER(abbreviation) AS abbreviation, {pct_cols}
                        FROM driver_features
                    ) ranked
                    WHERE abbreviation = :code
                    ORDER BY season
                    """
                ),
                {"code": code},
            )
            .mappings()
            .all()
        )

    has_career = bool(career and career["grands_prix"])
    if not identity and not has_career:
        return {"error": f"No data for driver {code}", "code": 404}, 404

    career_out = None
    if has_career:
        career_out = {k: career[k] for k in career.keys()}
        career_out["career_points"] = float(career_out["career_points"])

    return jsonify(
        {
            "code": code,
            "identity": dict(identity) if identity else None,
            "career": career_out,
            "recent_races": [
                {**dict(r), "race_date": r["race_date"].isoformat() if r["race_date"] else None}
                for r in recent
            ],
            "style": dict(style) if style else None,
            "seasons": [
                {**dict(r), "points": float(r["points"])} for r in seasons
            ],
            "results_grid": [
                {**dict(r), "points": float(r["points"] or 0)} for r in grid
            ],
            "style_history": [
                {k: (float(v) if isinstance(v, (int, float)) and k != "season" else v)
                 for k, v in dict(r).items() if k != "abbreviation"}
                for r in style_history
            ],
        }
    )
