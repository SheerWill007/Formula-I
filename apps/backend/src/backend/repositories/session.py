"""
Session repository for database operations.
"""
from typing import List, Optional
from sqlalchemy import select, func, case
from sqlalchemy.orm import Session as DBSession, joinedload

from backend.models.session import Session
from backend.repositories.base import BaseRepository


class SessionRepository(BaseRepository[Session]):
    """Repository for session-related database operations."""

    def __init__(self, db: DBSession):
        super().__init__(Session, db)

    def get_by_session_key(self, session_key: int) -> Optional[Session]:
        """Get session by session_key with drivers preloaded."""
        stmt = (
            select(Session)
            .where(Session.session_key == session_key)
            .options(joinedload(Session.drivers))
        )
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def list_all_ordered(self) -> List[Session]:
        """
        List all sessions ordered by date descending.
        Qualifying sessions appear before Race sessions on the same date.
        """
        # Session type priority for same-date ordering
        session_type_priority = case(
            (Session.session_type == "Q", 1),
            (Session.session_type == "SQ", 2),
            (Session.session_type == "S", 3),
            (Session.session_type == "R", 4),
            else_=5
        )
        
        stmt = (
            select(Session)
            .order_by(
                Session.date_start.desc().nulls_last(),
                session_type_priority
            )
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def get_by_year_and_gp(self, year: int, gp_name: str) -> List[Session]:
        """Get all sessions for a specific year and Grand Prix."""
        stmt = (
            select(Session)
            .where(Session.year == year, Session.gp_name == gp_name)
            .order_by(Session.date_start)
        )
        result = self.db.execute(stmt)
        return list(result.scalars().all())

    def get_latest_qualifying(self) -> Optional[Session]:
        """Get the most recent qualifying session."""
        stmt = (
            select(Session)
            .where(Session.session_type.in_(["Q", "SQ"]))
            .order_by(Session.date_start.desc())
            .limit(1)
        )
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def get_latest_race(self) -> Optional[Session]:
        """Get the most recent race session."""
        stmt = (
            select(Session)
            .where(Session.session_type == "R")
            .order_by(Session.date_start.desc())
            .limit(1)
        )
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def exists(self, session_key: int) -> bool:
        """Check if a session exists."""
        stmt = select(func.count()).select_from(Session).where(Session.session_key == session_key)
        result = self.db.execute(stmt)
        return result.scalar() > 0
