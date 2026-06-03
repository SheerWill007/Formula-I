"""
Race analysis service layer.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text

from backend.repositories.lap_time import LapTimeRepository
from backend.repositories.driver import DriverRepository
from backend.schemas.race import RaceResultResponse


class RaceService:
    """Service for race-related business logic."""

    def __init__(self, db: DBSession):
        self.db = db
        self.lap_repo = LapTimeRepository(db)
        self.driver_repo = DriverRepository(db)

    def get_race_results(self, session_key: int) -> List[RaceResultResponse]:
        """
        Get race finishing order with gaps.
        Uses position column from live timing data.
        """
        # Check if position data exists
        has_position_query = text("""
            SELECT COUNT(*) FROM lap_times
            WHERE session_key = :sk AND position IS NOT NULL
        """)
        has_position = self.db.execute(has_position_query, {"sk": session_key}).scalar()

        if has_position:
            query = text("""
                WITH final_lap AS (
                    SELECT DISTINCT ON (l.driver_number)
                        l.driver_number,
                        l.lap_number AS total_laps,
                        l.position AS finish_pos,
                        l.compound,
                        l.lap_time_ms AS last_lap_ms
                    FROM lap_times l
                    WHERE l.session_key = :sk
                    ORDER BY l.driver_number, l.lap_number DESC
                ),
                best_lap AS (
                    SELECT driver_number, MIN(lap_time_ms) AS best_lap_ms
                    FROM lap_times
                    WHERE session_key = :sk AND lap_time_ms IS NOT NULL
                    GROUP BY driver_number
                ),
                race_time AS (
                    SELECT driver_number, SUM(lap_time_ms) AS total_ms
                    FROM lap_times
                    WHERE session_key = :sk AND lap_time_ms IS NOT NULL AND deleted = FALSE
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
                    bl.best_lap_ms,
                    rt.total_ms
                FROM final_lap fl
                JOIN drivers d ON d.driver_number = fl.driver_number AND d.session_key = :sk
                JOIN best_lap bl ON bl.driver_number = fl.driver_number
                LEFT JOIN race_time rt ON rt.driver_number = fl.driver_number
                ORDER BY fl.finish_pos ASC NULLS LAST, fl.total_laps DESC
            """)
        else:
            # Fallback: order by laps completed then cumulative time
            query = text("""
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
            """)

        result = self.db.execute(query, {"sk": session_key})
        rows = result.mappings().all()

        if not rows:
            return []

        results = [dict(row) for row in rows]

        # Calculate gaps to winner
        winner_total = results[0].get("total_ms")
        max_laps = results[0].get("total_laps", 0)

        for i, r in enumerate(results):
            driver_total = r.get("total_ms")
            if i == 0:
                r["gap_ms"] = None
                r["laps_down"] = 0
            elif r.get("total_laps", 0) < max_laps:
                r["gap_ms"] = None
                r["laps_down"] = int(max_laps - r.get("total_laps", 0))
            elif driver_total and winner_total:
                r["gap_ms"] = float(driver_total - winner_total)
                r["laps_down"] = 0
            else:
                r["gap_ms"] = None
                r["laps_down"] = 0

        return [RaceResultResponse(**r) for r in results]
