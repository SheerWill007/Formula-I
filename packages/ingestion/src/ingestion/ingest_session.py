import argparse
import structlog
from ingestion.fastf1_client import (
    fetch_session, extract_session_info,
    extract_drivers, extract_laps, extract_telemetry,
)
from ingestion.loader import (
    upsert_session, load_drivers, load_laps,
    load_telemetry, update_session_weather,
)

log = structlog.get_logger()

SESSION_MAP = {
    'Q':   'Qualifying',
    'R':   'Race',
    'SQ':  'Sprint Qualifying',
    'S':   'Sprint',
    'FP1': 'Practice 1',
    'FP2': 'Practice 2',
    'FP3': 'Practice 3',
}


def extract_weather(session) -> dict:
    """
    Extract weather snapshot from end of session.
    Returns dict with track_temp, air_temp, humidity, rainfall, wind_speed.
    """
    try:
        wx = session.weather_data
        if wx is None or wx.empty:
            return {}
        # Use last row — most representative of race/session conditions
        last = wx.iloc[-1]
        return {
            'track_temp': float(last.get('TrackTemp', 0)) or None,
            'air_temp':   float(last.get('AirTemp', 0))   or None,
            'humidity':   float(last.get('Humidity', 0))  or None,
            'rainfall':   bool(last.get('Rainfall', False)),
            'wind_speed': float(last.get('WindSpeed', 0)) or None,
        }
    except Exception as e:
        log.warning("weather.extraction_failed", error=str(e))
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--year',           type=int, required=True)
    parser.add_argument('--gp',             type=str, required=True)
    parser.add_argument('--session',        type=str, required=True,
                        help="Q, R, SQ, S, FP1, FP2, FP3")
    parser.add_argument('--skip-telemetry', action='store_true')
    args = parser.parse_args()

    fastf1_session = SESSION_MAP.get(args.session.upper(), args.session)

    log.info("ingest.start",
             year=args.year, gp=args.gp,
             session=args.session, fastf1_name=fastf1_session)

    session      = fetch_session(args.year, args.gp, fastf1_session)
    session_info = extract_session_info(session)
    session_key  = upsert_session(session_info)

    # Weather
    weather = extract_weather(session)
    if weather:
        update_session_weather(session_key, **weather)
        log.info("ingest.weather_stored",
                 track_temp=weather.get('track_temp'),
                 air_temp=weather.get('air_temp'))

    drivers   = extract_drivers(session, session_key)
    load_drivers(drivers)

    laps      = extract_laps(session, session_key)
    lap_count = load_laps(laps, session_key)

    tel_count = 0
    TELEMETRY_SESSIONS = {'Q', 'SQ'}  # qualifying only — keeps DB lean
    if not args.skip_telemetry and args.session.upper() in TELEMETRY_SESSIONS:
        tel       = extract_telemetry(session, session_key, all_drivers=True)
        tel_count = load_telemetry(tel, session_key)
    elif not args.skip_telemetry and args.session.upper() not in TELEMETRY_SESSIONS:
        log.info("telemetry.skipped",
                 reason="non-qualifying session — telemetry not stored by design",
                 session=args.session)

    print(f"\n✅  session={session_key}  drivers={len(drivers)}"
          f"  laps={lap_count}  telemetry={tel_count}"
          f"  weather={'yes' if weather else 'no'}")


if __name__ == '__main__':
    main()
