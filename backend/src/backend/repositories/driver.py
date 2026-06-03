"""
Driver repository for database operations.
"""
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from backend.models.driver import Driver
from backend.repositories.base import BaseRepository


class DriverRepository(BaseRepository[Driver]):
    """Repository for driver-related database operations."""

    def __init__(self, db: DBSession):
        super().__init__(Driver, db)

    def get_by_session(self, session_key: int) -> List[Driver]:
        """Get all drivers for a specific session."""
        stmt = (
            select(Driver)
            .where(Driver.session_key == session_key)
            .order_by(Driver.driver_number)
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def get_by_session_and_number(
        self, session_key: int, driver_number: int
    ) -> Optional[Driver]:
        """Get a specific driver for a session."""
        stmt = select(Driver).where(
            Driver.session_key == session_key,
            Driver.driver_number == driver_number
        )
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def get_by_numbers(self, session_key: int, driver_numbers: List[int]) -> List[Driver]:
        """Get multiple drivers by their numbers for a specific session."""
        stmt = (
            select(Driver)
            .where(
                Driver.session_key == session_key,
                Driver.driver_number.in_(driver_numbers)
            )
            .order_by(Driver.driver_number)
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())
