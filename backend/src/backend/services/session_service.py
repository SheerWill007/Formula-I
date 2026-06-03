"""
Session service layer for business logic.
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session as DBSession

from backend.repositories.session import SessionRepository
from backend.repositories.driver import DriverRepository
from backend.models.session import Session
from backend.schemas.session import SessionResponse, SessionDetailResponse


class SessionService:
    """Service for session-related business logic."""

    def __init__(self, db: DBSession):
        self.db = db
        self.session_repo = SessionRepository(db)
        self.driver_repo = DriverRepository(db)

    def list_sessions(self) -> List[SessionResponse]:
        """List all sessions ordered by date descending."""
        sessions = self.session_repo.list_all_ordered()
        return [SessionResponse.from_orm(session) for session in sessions]

    def get_session_detail(self, session_key: int) -> Optional[SessionDetailResponse]:
        """Get session with drivers."""
        session = self.session_repo.get_by_session_key(session_key)
        if not session:
            return None
        
        drivers = self.driver_repo.get_by_session(session_key)
        return SessionDetailResponse.from_orm_with_drivers(session, drivers)

    def session_exists(self, session_key: int) -> bool:
        """Check if a session exists."""
        return self.session_repo.exists(session_key)

    def get_latest_qualifying(self) -> Optional[SessionResponse]:
        """Get the most recent qualifying session."""
        session = self.session_repo.get_latest_qualifying()
        return SessionResponse.from_orm(session) if session else None

    def get_latest_race(self) -> Optional[SessionResponse]:
        """Get the most recent race session."""
        session = self.session_repo.get_latest_race()
        return SessionResponse.from_orm(session) if session else None
