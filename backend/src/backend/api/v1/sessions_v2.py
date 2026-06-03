"""
Sessions API routes - refactored version using service/repository pattern.
"""
from flask import Blueprint, jsonify, request
import structlog
import requests

from backend.database import get_db
from backend.services.session_service import SessionService
from backend.services.race_service import RaceService
from backend.exceptions import ResourceNotFoundError, ExternalAPIError

log = structlog.get_logger()

sessions_v2_bp = Blueprint("sessions_v2", __name__)


@sessions_v2_bp.get("/sessions")
def list_sessions():
    """
    List all sessions ordered by date descending.
    Qualifying sessions appear before Race sessions on the same date.
    """
    db = next(get_db())
    try:
        service = SessionService(db)
        sessions = service.list_sessions()
        return jsonify([s.model_dump(mode='json') for s in sessions])
    finally:
        db.close()


@sessions_v2_bp.get("/sessions/<int:session_key>")
def get_session(session_key: int):
    """Get session detail with drivers."""
    db = next(get_db())
    try:
        service = SessionService(db)
        session = service.get_session_detail(session_key)
        
        if not session:
            raise ResourceNotFoundError("Session", session_key)
        
        return jsonify(session.model_dump(mode='json'))
    finally:
        db.close()


@sessions_v2_bp.get("/sessions/<int:session_key>/race-results")
def race_results(session_key: int):
    """
    Race finishing order with gaps.
    Uses position column from live timing data.
    """
    db = next(get_db())
    try:
        # Verify session exists
        session_service = SessionService(db)
        if not session_service.session_exists(session_key):
            raise ResourceNotFoundError("Session", session_key)
        
        # Get race results
        race_service = RaceService(db)
        results = race_service.get_race_results(session_key)
        
        return jsonify([r.model_dump(mode='json') for r in results])
    finally:
        db.close()


# ── Championship standings via Jolpica-F1 (official data) ────────────────────


@sessions_v2_bp.get("/standings/drivers")
def driver_standings():
    """
    Official driver championship standings via Jolpica-F1 API.
    Query param: ?year=2026 (default: current year)
    """
    import requests

    year = request.args.get("year", 2026, type=int)

    try:
        url = f"http://api.jolpi.ca/ergast/f1/{year}/driverStandings.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        standings_table = data.get("MRData", {}).get("StandingsTable", {})
        standings_lists = standings_table.get("StandingsLists", [])
        
        if not standings_lists:
            return jsonify({"year": year, "round": 0, "standings": []})
        
        latest_round_data = standings_lists[-1]
        driver_standings_list = latest_round_data.get("DriverStandings", [])
        
        standings = []
        for entry in driver_standings_list:
            driver = entry.get("Driver", {})
            constructors = entry.get("Constructors", [{}])
            team_name = constructors[0].get("name", "") if constructors else ""
            standings.append({
                "position": int(entry.get("position", 0)),
                "points": float(entry.get("points", 0)),
                "wins": int(entry.get("wins", 0)),
                "code": driver.get("code"),
                "full_name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip(),
                "nationality": driver.get("nationality"),
                "team_name": team_name,
            })
        
        return jsonify({
            "year": year,
            "round": int(latest_round_data.get("round", 0)),
            "standings": standings,
        })

    except requests.RequestException as e:
        log.warning("jolpica_api_error", error=str(e))
        raise ExternalAPIError("Jolpica F1 API", str(e))


@sessions_v2_bp.get("/standings/constructors")
def constructor_standings():
    """
    Official constructor championship standings via Jolpica-F1 API.
    Query param: ?year=2026
    """
    import requests

    year = request.args.get("year", 2026, type=int)

    try:
        url = f"http://api.jolpi.ca/ergast/f1/{year}/constructorStandings.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        standings_table = data.get("MRData", {}).get("StandingsTable", {})
        standings_lists = standings_table.get("StandingsLists", [])
        
        if not standings_lists:
            return jsonify({"year": year, "round": 0, "standings": []})
        
        latest_round_data = standings_lists[-1]
        constructor_standings_list = latest_round_data.get("ConstructorStandings", [])
        
        standings = []
        for entry in constructor_standings_list:
            constructor = entry.get("Constructor", {})
            standings.append({
                "position": int(entry.get("position", 0)),
                "points": float(entry.get("points", 0)),
                "wins": int(entry.get("wins", 0)),
                "team_name": constructor.get("name"),
                "nationality": constructor.get("nationality"),
            })
        
        return jsonify({
            "year": year,
            "round": int(latest_round_data.get("round", 0)),
            "standings": standings,
        })

    except requests.RequestException as e:
        log.warning("jolpica_api_error", error=str(e))
        raise ExternalAPIError("Jolpica F1 API", str(e))
