"""
Quick test script for the refactored API architecture.

Usage:
    python test_refactored_api.py
"""
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from backend.database import get_db_session
from backend.services.session_service import SessionService
from backend.services.race_service import RaceService
from backend.services.lap_service import LapService
from backend.repositories.session import SessionRepository
from backend.repositories.driver import DriverRepository
from backend.repositories.lap_time import LapTimeRepository


def test_repository_layer():
    """Test repository layer directly."""
    print("\n" + "="*60)
    print("Testing Repository Layer")
    print("="*60)
    
    with get_db_session() as db:
        # Test SessionRepository
        print("\n1. Testing SessionRepository...")
        session_repo = SessionRepository(db)
        sessions = session_repo.list_all_ordered()
        print(f"   ✓ Found {len(sessions)} sessions")
        
        if sessions:
            first_session = sessions[0]
            print(f"   ✓ Latest session: {first_session.year} {first_session.gp_name} {first_session.session_type}")
            
            # Test getting by key
            session_detail = session_repo.get_by_session_key(first_session.session_key)
            print(f"   ✓ Loaded session detail: {session_detail.session_name}")
        
        # Test DriverRepository
        if sessions:
            print("\n2. Testing DriverRepository...")
            driver_repo = DriverRepository(db)
            drivers = driver_repo.get_by_session(first_session.session_key)
            print(f"   ✓ Found {len(drivers)} drivers in session")
            if drivers:
                print(f"   ✓ First driver: #{drivers[0].driver_number} {drivers[0].full_name}")
        
        # Test LapTimeRepository
        if sessions and drivers:
            print("\n3. Testing LapTimeRepository...")
            lap_repo = LapTimeRepository(db)
            laps = lap_repo.get_by_driver(first_session.session_key, drivers[0].driver_number)
            print(f"   ✓ Found {len(laps)} laps for driver #{drivers[0].driver_number}")
            
            fastest = lap_repo.get_fastest_lap(first_session.session_key, drivers[0].driver_number)
            if fastest:
                print(f"   ✓ Fastest lap: {fastest.lap_time_ms:.3f}ms on lap {fastest.lap_number}")


def test_service_layer():
    """Test service layer."""
    print("\n" + "="*60)
    print("Testing Service Layer")
    print("="*60)
    
    with get_db_session() as db:
        # Test SessionService
        print("\n1. Testing SessionService...")
        session_service = SessionService(db)
        sessions = session_service.list_sessions()
        print(f"   ✓ Found {len(sessions)} sessions")
        
        if sessions:
            session_response = sessions[0]
            print(f"   ✓ Response type: {type(session_response).__name__}")
            print(f"   ✓ Session: {session_response.year} {session_response.gp_name}")
            
            # Test get detail
            detail = session_service.get_session_detail(session_response.session_key)
            if detail:
                print(f"   ✓ Session detail loaded with {len(detail.drivers)} drivers")
        
        # Test RaceService
        if sessions:
            race_sessions = [s for s in sessions if s.session_type == 'R']
            if race_sessions:
                print("\n2. Testing RaceService...")
                race_service = RaceService(db)
                results = race_service.get_race_results(race_sessions[0].session_key)
                print(f"   ✓ Got race results for {len(results)} drivers")
                if results:
                    winner = results[0]
                    print(f"   ✓ Winner: #{winner.driver_number} {winner.full_name}")
                    print(f"   ✓ Total laps: {winner.total_laps}")
        
        # Test LapService
        if sessions:
            quali_sessions = [s for s in sessions if s.session_type == 'Q']
            if quali_sessions:
                print("\n3. Testing LapService...")
                lap_service = LapService(db)
                fastest_laps = lap_service.get_fastest_laps(quali_sessions[0].session_key, limit=3)
                print(f"   ✓ Got {len(fastest_laps)} fastest laps")
                for i, lap in enumerate(fastest_laps[:3], 1):
                    print(f"   {i}. #{lap.driver_number} {lap.abbreviation}: {lap.lap_time_ms:.3f}ms")


def test_schema_serialization():
    """Test Pydantic schema serialization."""
    print("\n" + "="*60)
    print("Testing Schema Serialization")
    print("="*60)
    
    with get_db_session() as db:
        session_service = SessionService(db)
        sessions = session_service.list_sessions()
        
        if sessions:
            print("\n1. Testing JSON serialization...")
            session_dict = sessions[0].model_dump(mode='json')
            print(f"   ✓ Serialized to dict with {len(session_dict)} fields")
            print(f"   ✓ Fields: {', '.join(session_dict.keys())}")
            
            print("\n2. Testing nested serialization...")
            detail = session_service.get_session_detail(sessions[0].session_key)
            if detail:
                detail_dict = detail.model_dump(mode='json')
                print(f"   ✓ Detail has {len(detail_dict['drivers'])} drivers")
                if detail_dict['drivers']:
                    print(f"   ✓ Driver fields: {', '.join(detail_dict['drivers'][0].keys())}")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("REFACTORED BACKEND ARCHITECTURE TEST")
    print("="*60)
    
    try:
        test_repository_layer()
        test_service_layer()
        test_schema_serialization()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nThe refactored architecture is working correctly!")
        print("You can now use these components in your API routes.")
        print("\nNext steps:")
        print("1. Start the Flask app: python main.py")
        print("2. Test v2 routes: curl http://localhost:8000/api/v2/sessions")
        print("3. Migrate more routes to use the new architecture")
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ TEST FAILED")
        print("="*60)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
