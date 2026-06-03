"""
Lap time service layer for business logic.
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text

from backend.repositories.lap_time import LapTimeRepository
from backend.repositories.driver import DriverRepository
from backend.schemas.lap import LapTimeResponse, FastestLapResponse


class LapService:
    """Service for lap time-related business logic."""

    def __init__(self, db: DBSession):
        self.db = db
        self.lap_repo = LapTimeRepository(db)
        self.driver_repo = DriverRepository(db)

    def get_fastest_laps(self, session_key: int, limit: int = 10) -> List[FastestLapResponse]:
        """Get fastest laps for a session."""
        # Use raw SQL for complex query with proper ordering
        query = text("""
            SELECT DISTINCT ON (l.driver_number)
                l.driver_number,
                l.lap_number,
                l.lap_time_ms,
                l.sector_1_ms,
                l.sector_2_ms,
                l.sector_3_ms,
                l.compound,
                l.quali_segment,
                d.full_name,
                d.abbreviation,
                d.team_name,
                d.team_colour
            FROM lap_times l
            JOIN drivers d ON d.driver_number = l.driver_number AND d.session_key = l.session_key
            WHERE l.session_key = :session_key
                AND l.lap_time_ms IS NOT NULL
                AND l.deleted = FALSE
            ORDER BY l.driver_number, l.lap_time_ms ASC
        """)
        
        result = self.db.execute(query, {"session_key": session_key})
        rows = result.mappings().all()
        
        # Sort by lap time and apply limit
        sorted_rows = sorted(rows, key=lambda x: x["lap_time_ms"] or float('inf'))[:limit]
        
        return [FastestLapResponse(**dict(row)) for row in sorted_rows]

    def get_driver_laps(
        self, session_key: int, driver_number: int, segment: Optional[str] = None
    ) -> List[LapTimeResponse]:
        """Get all laps for a driver, optionally filtered by qualifying segment."""
        if segment:
            laps = self.lap_repo.get_by_quali_segment(session_key, segment, [driver_number])
        else:
            laps = self.lap_repo.get_by_driver(session_key, driver_number)
        
        return [LapTimeResponse.from_orm(lap) for lap in laps]

    def get_lap_comparison(
        self, session_key: int, driver_numbers: List[int], segment: Optional[str] = None
    ) -> Dict[str, List[LapTimeResponse]]:
        """Get laps for multiple drivers for comparison."""
        result = {}
        for driver_number in driver_numbers:
            laps = self.get_driver_laps(session_key, driver_number, segment)
            result[str(driver_number)] = laps
        return result
