"""
LapTime repository for database operations.
"""
from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session as DBSession

from backend.models.lap_time import LapTime
from backend.repositories.base import BaseRepository


class LapTimeRepository(BaseRepository[LapTime]):
    """Repository for lap time-related database operations."""

    def __init__(self, db: DBSession):
        super().__init__(LapTime, db)

    def get_by_session(self, session_key: int) -> List[LapTime]:
        """Get all lap times for a session."""
        stmt = (
            select(LapTime)
            .where(LapTime.session_key == session_key)
            .order_by(LapTime.lap_number, LapTime.driver_number)
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def get_by_driver(self, session_key: int, driver_number: int) -> List[LapTime]:
        """Get all lap times for a specific driver in a session."""
        stmt = (
            select(LapTime)
            .where(
                LapTime.session_key == session_key,
                LapTime.driver_number == driver_number
            )
            .order_by(LapTime.lap_number)
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def get_fastest_lap(self, session_key: int, driver_number: int) -> Optional[LapTime]:
        """Get the fastest lap for a driver in a session."""
        stmt = (
            select(LapTime)
            .where(
                LapTime.session_key == session_key,
                LapTime.driver_number == driver_number,
                LapTime.lap_time_ms.isnot(None),
                LapTime.deleted == False
            )
            .order_by(LapTime.lap_time_ms)
            .limit(1)
        )
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def get_by_quali_segment(
        self, session_key: int, segment: str, driver_numbers: Optional[List[int]] = None
    ) -> List[LapTime]:
        """Get lap times for a specific qualifying segment (Q1, Q2, Q3)."""
        stmt = select(LapTime).where(
            LapTime.session_key == session_key,
            LapTime.quali_segment == segment
        )
        
        if driver_numbers:
            stmt = stmt.where(LapTime.driver_number.in_(driver_numbers))
        
        stmt = stmt.order_by(LapTime.driver_number, LapTime.lap_number)
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def get_final_lap_per_driver(self, session_key: int) -> List[LapTime]:
        """Get the final lap for each driver in a session (for race results)."""
        # Use window function to get the last lap per driver
        from sqlalchemy import over
        
        stmt = (
            select(LapTime)
            .where(LapTime.session_key == session_key)
            .distinct(LapTime.driver_number)
            .order_by(LapTime.driver_number, LapTime.lap_number.desc())
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def count_laps_by_driver(self, session_key: int, driver_number: int) -> int:
        """Count total laps completed by a driver."""
        stmt = (
            select(func.count())
            .select_from(LapTime)
            .where(
                LapTime.session_key == session_key,
                LapTime.driver_number == driver_number
            )
        )
        result = self.db.execute(stmt)
        return result.scalar() or 0

    def get_long_runs(self, session_key: int, min_laps: int = 5) -> List[dict]:
        """Get stints with at least min_laps consecutive laps."""
        # This would require more complex logic - placeholder for now
        # In a real implementation, you'd analyze consecutive laps per driver
        return []
