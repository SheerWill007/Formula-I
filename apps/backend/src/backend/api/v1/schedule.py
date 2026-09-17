"""
schedule.py — /api/v1/schedule/*
Serves 2026 F1 calendar with session times.
FastF1 schedule is loaded ONCE at import time and cached in memory.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache

import fastf1
from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

schedule_bp = Blueprint("schedule", __name__)

# ---------------------------------------------------------------------------
# Country → flag emoji map  (ISO 3166-1 alpha-2 → flag)
# ---------------------------------------------------------------------------
COUNTRY_FLAGS: dict[str, str] = {
    "Australia": "🇦🇺",
    "China": "🇨🇳",
    "Japan": "🇯🇵",
    "Bahrain": "🇧🇭",
    "Saudi Arabia": "🇸🇦",
    "United States": "🇺🇸",
    "USA": "🇺🇸",
    "Italy": "🇮🇹",
    "Monaco": "🇲🇨",
    "Canada": "🇨🇦",
    "Spain": "🇪🇸",
    "Austria": "🇦🇹",
    "United Kingdom": "🇬🇧",
    "Hungary": "🇭🇺",
    "Belgium": "🇧🇪",
    "Netherlands": "🇳🇱",
    "Singapore": "🇸🇬",
    "Mexico": "🇲🇽",
    "Brazil": "🇧🇷",
    "Qatar": "🇶🇦",
    "UAE": "🇦🇪",
    "Abu Dhabi": "🇦🇪",
    "Azerbaijan": "🇦🇿",
    "Miami": "🇺🇸",
    "Las Vegas": "🇺🇸",
}

# ---------------------------------------------------------------------------
# Circuit names — FastF1 uses EventName like "Japanese Grand Prix"
# We map to the iconic circuit name for display
# ---------------------------------------------------------------------------
CIRCUIT_NAMES: dict[str, str] = {
    "Australian Grand Prix": "Albert Park",
    "Chinese Grand Prix": "Shanghai International Circuit",
    "Japanese Grand Prix": "Suzuka Circuit",
    "Bahrain Grand Prix": "Bahrain International Circuit",
    "Saudi Arabian Grand Prix": "Jeddah Corniche Circuit",
    "Miami Grand Prix": "Miami International Autodrome",
    "Emilia Romagna Grand Prix": "Autodromo Enzo e Dino Ferrari",
    "Monaco Grand Prix": "Circuit de Monaco",
    "Spanish Grand Prix": "Circuit de Barcelona-Catalunya",
    "Canadian Grand Prix": "Circuit Gilles Villeneuve",
    "Austrian Grand Prix": "Red Bull Ring",
    "British Grand Prix": "Silverstone Circuit",
    "Hungarian Grand Prix": "Hungaroring",
    "Belgian Grand Prix": "Circuit de Spa-Francorchamps",
    "Dutch Grand Prix": "Circuit Zandvoort",
    "Italian Grand Prix": "Autodromo Nazionale Monza",
    "Azerbaijan Grand Prix": "Baku City Circuit",
    "Singapore Grand Prix": "Marina Bay Street Circuit",
    "United States Grand Prix": "Circuit of the Americas",
    "Mexico City Grand Prix": "Autodromo Hermanos Rodriguez",
    "São Paulo Grand Prix": "Autodromo Jose Carlos Pace",
    "Las Vegas Grand Prix": "Las Vegas Strip Circuit",
    "Qatar Grand Prix": "Lusail International Circuit",
    "Abu Dhabi Grand Prix": "Yas Marina Circuit",
}


@lru_cache(maxsize=1)
def _load_schedule() -> list[dict]:
    """
    Load FastF1 2026 schedule ONCE. lru_cache means this only runs on the
    first call — every subsequent call returns the cached result instantly.
    """
    log.info("Loading 2026 F1 schedule from FastF1 (first call only)...")
    try:
        fastf1.Cache.enable_cache("/tmp/fastf1_cache")
    except Exception:
        pass  # cache optional

    sched = fastf1.get_event_schedule(2026, include_testing=False)
    races = []

    for _, row in sched.iterrows():
        sessions = []

        # FastF1 3.x uses Session1..Session5 + Session1Date..Session5Date
        for i in range(1, 6):
            s_name = row.get(f"Session{i}", "")
            s_date = row.get(f"Session{i}Date")

            if not s_name or str(s_name).strip() == "" or s_name == "None":
                continue

            # Pandas Timestamp → ISO 8601 UTC string
            if s_date is not None and str(s_date) != "NaT":
                try:
                    import pandas as pd
                    ts = pd.Timestamp(s_date)
                    if ts.tzinfo is None:
                        ts = ts.tz_localize("UTC")
                    else:
                        ts = ts.tz_convert("UTC")
                    date_str = ts.isoformat()
                except Exception:
                    date_str = str(s_date)
            else:
                date_str = None

            sessions.append({"name": str(s_name), "date_utc": date_str})

        country = str(row.get("Country", ""))
        event_name = str(row.get("EventName", ""))

        races.append(
            {
                "round": int(row.get("RoundNumber", 0)),
                "event_name": event_name,
                "circuit": CIRCUIT_NAMES.get(event_name, str(row.get("Location", ""))),
                "country": country,
                "flag": COUNTRY_FLAGS.get(country, "🏁"),
                "event_date": str(row.get("EventDate", "")),
                "sessions": sessions,
            }
        )

    log.info(f"Schedule loaded: {len(races)} races")
    return races


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _find_next_session(races: list[dict]) -> tuple[dict | None, dict | None]:
    """Return (race, session) for the upcoming or currently active session."""
    now = _now_utc()
    from datetime import datetime as dt, timedelta
    from datetime import timezone as tz

    for race in races:
        for session in race["sessions"]:
            if not session["date_utc"]:
                continue
            try:
                session_time = dt.fromisoformat(session["date_utc"])
                if session_time.tzinfo is None:
                    session_time = session_time.replace(tzinfo=tz.utc)

                # If session started within the last 2 hours, it's "LIVE"
                # If it's in the future, it's "UPCOMING"
                if session_time > (now - timedelta(hours=2)):
                    return race, session
            except Exception:
                continue
    return None, None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_results(year: int) -> dict[int, list[str]]:
    """Fetch Top 3 finishers for all rounds of the season."""
    log.info(f"Loading {year} race results from Ergast...")
    try:
        from fastf1.ergast import Ergast
        ergast = Ergast()
        # Get all race results for the season
        results = ergast.get_race_results(season=year, result_type='raw')
        
        round_results = {}
        for round_data in results:
            r_num = int(round_data.get("round", 0))
            drivers = round_data.get("Results", [])[:3]
            round_results[r_num] = [d.get("Driver", {}).get("code", "???") for d in drivers]
        return round_results
    except Exception as e:
        log.warning(f"Failed to load race results: {e}")
        return {}


@schedule_bp.route("/schedule/next-race", methods=["GET"])
def next_race():
    """
    Returns the next upcoming race weekend + which session is next.
    Used by the home page countdown card.
    """
    races = _load_schedule()
    next_race_data, next_session = _find_next_session(races)

    # Fallback: if session-level lookup fails, return the next race day that is
    # still ahead of us. This keeps the endpoint usable even if a session time
    # is missing or malformed.
    if not next_race_data:
        now = _now_utc()
        for race in races:
            try:
                from datetime import datetime as dt
                race_date_str = race["event_date"]
                race_dt = dt.fromisoformat(str(race_date_str).split(" ")[0])
                if race_dt.date() > now.date():
                    next_race_data = race
                    break
            except Exception:
                continue

    if not next_race_data:
        return jsonify({"error": "No upcoming races found"}), 404

    return jsonify(
        {
            "race": next_race_data,
            "next_session": next_session,
        }
    )


@schedule_bp.route("/schedule/2026", methods=["GET"])
def full_schedule():
    """
    Returns the complete 2026 F1 calendar enrichment with Top 3 winners.
    """
    races = _load_schedule()
    results = _load_results(2026)
    now = _now_utc()

    # Tag each race as past / current / upcoming
    enriched = []
    for race in races:
        try:
            from datetime import datetime as dt
            race_dt = dt.fromisoformat(str(race["event_date"]).split(" ")[0])
            if race_dt.date() < now.date():
                status = "past"
            elif race_dt.date() == now.date():
                status = "live"
            else:
                status = "upcoming"
        except Exception:
            status = "upcoming"

        # Add dynamic top finishers from season results
        race_results = results.get(race["round"], [])
        enriched.append({**race, "status": status, "top_finishers": race_results})

    return jsonify({"season": 2026, "total_rounds": len(enriched), "races": enriched})
