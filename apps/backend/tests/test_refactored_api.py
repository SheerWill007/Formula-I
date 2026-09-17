"""
Tests for the refactored API architecture (repositories, services, schemas).
"""
import sys
import os
import pytest

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from backend.database import get_db_session
from backend.services.session_service import SessionService
from backend.services.race_service import RaceService
from backend.services.lap_service import LapService
from backend.repositories.session import SessionRepository
from backend.repositories.driver import DriverRepository
from backend.repositories.lap_time import LapTimeRepository


class TestRepositoryLayer:
    """Test repository layer directly."""

    def test_session_repository(self):
        """Test SessionRepository list_all_ordered."""
        with get_db_session() as db:
            session_repo = SessionRepository(db)
            sessions = session_repo.list_all_ordered()
            assert sessions is not None
            assert isinstance(sessions, list)

    def test_session_repository_get_by_key(self):
        """Test SessionRepository get_by_session_key."""
        with get_db_session() as db:
            session_repo = SessionRepository(db)
            sessions = session_repo.list_all_ordered()
            
            if sessions:
                session_detail = session_repo.get_by_session_key(sessions[0].session_key)
                assert session_detail is not None
                assert session_detail.session_name is not None

    def test_driver_repository(self):
        """Test DriverRepository get_by_session."""
        with get_db_session() as db:
            session_repo = SessionRepository(db)
            sessions = session_repo.list_all_ordered()
            
            if sessions:
                driver_repo = DriverRepository(db)
                drivers = driver_repo.get_by_session(sessions[0].session_key)
                assert drivers is not None
                assert isinstance(drivers, list)

    def test_lap_time_repository(self):
        """Test LapTimeRepository get_by_driver."""
        with get_db_session() as db:
            session_repo = SessionRepository(db)
            sessions = session_repo.list_all_ordered()
            
            if sessions:
                driver_repo = DriverRepository(db)
                drivers = driver_repo.get_by_session(sessions[0].session_key)
                
                if drivers:
                    lap_repo = LapTimeRepository(db)
                    laps = lap_repo.get_by_driver(sessions[0].session_key, drivers[0].driver_number)
                    assert laps is not None
                    assert isinstance(laps, list)

    def test_lap_time_fastest_lap(self):
        """Test LapTimeRepository get_fastest_lap."""
        with get_db_session() as db:
            session_repo = SessionRepository(db)
            sessions = session_repo.list_all_ordered()
            
            if sessions:
                driver_repo = DriverRepository(db)
                drivers = driver_repo.get_by_session(sessions[0].session_key)
                
                if drivers:
                    lap_repo = LapTimeRepository(db)
                    fastest = lap_repo.get_fastest_lap(sessions[0].session_key, drivers[0].driver_number)
                    # fastest may be None if no valid laps
                    if fastest:
                        assert fastest.lap_time_ms is not None
                        assert fastest.lap_number is not None


class TestServiceLayer:
    """Test service layer."""

    def test_session_service_list(self):
        """Test SessionService list_sessions."""
        with get_db_session() as db:
            session_service = SessionService(db)
            sessions = session_service.list_sessions()
            assert sessions is not None
            assert isinstance(sessions, list)

    def test_session_service_detail(self):
        """Test SessionService get_session_detail."""
        with get_db_session() as db:
            session_service = SessionService(db)
            sessions = session_service.list_sessions()
            
            if sessions:
                detail = session_service.get_session_detail(sessions[0].session_key)
                if detail:
                    assert detail.drivers is not None
                    assert isinstance(detail.drivers, list)

    def test_race_service(self):
        """Test RaceService get_race_results."""
        with get_db_session() as db:
            session_service = SessionService(db)
            sessions = session_service.list_sessions()
            race_sessions = [s for s in sessions if s.session_type == 'R']
            
            if race_sessions:
                race_service = RaceService(db)
                results = race_service.get_race_results(race_sessions[0].session_key)
                assert results is not None
                assert isinstance(results, list)

    def test_lap_service(self):
        """Test LapService get_fastest_laps."""
        with get_db_session() as db:
            session_service = SessionService(db)
            sessions = session_service.list_sessions()
            quali_sessions = [s for s in sessions if s.session_type == 'Q']
            
            if quali_sessions:
                lap_service = LapService(db)
                fastest_laps = lap_service.get_fastest_laps(quali_sessions[0].session_key, limit=3)
                assert fastest_laps is not None
                assert isinstance(fastest_laps, list)


class TestSchemaSerialization:
    """Test Pydantic schema serialization."""

    def test_session_serialization(self):
        """Test Session schema JSON serialization."""
        with get_db_session() as db:
            session_service = SessionService(db)
            sessions = session_service.list_sessions()
            
            if sessions:
                session_dict = sessions[0].model_dump(mode='json')
                assert isinstance(session_dict, dict)
                assert 'session_key' in session_dict
                assert 'year' in session_dict
                assert 'gp_name' in session_dict

    def test_session_detail_serialization(self):
        """Test SessionDetail schema JSON serialization with nested drivers."""
        with get_db_session() as db:
            session_service = SessionService(db)
            sessions = session_service.list_sessions()
            
            if sessions:
                detail = session_service.get_session_detail(sessions[0].session_key)
                if detail:
                    detail_dict = detail.model_dump(mode='json')
                    assert isinstance(detail_dict, dict)
                    assert 'drivers' in detail_dict
                    assert isinstance(detail_dict['drivers'], list)
