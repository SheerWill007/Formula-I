import argparse
import structlog
from ingestion.fastf1_client import (
    fetch_session,
    extract_session_info,
    extract_drivers,
    extract_laps,
    extract_telemetry,
    extract_race_control,
    extract_weather_events,
    extract_session_results,
    extract_track_status,
    _lap_start_times,
    _lap_for_timestamp,
)
from ingestion.loader import (
    upsert_session,
    load_drivers,
    load_laps,
    load_telemetry,
    update_session_weather,
    load_race_control,
    load_team_radio,
    load_weather_events,
    load_session_results,
    load_track_status,
    load_session_intervals,
    load_position_changes,
    load_pit_stops,
)
from ingestion.openf1_client import (
    fetch_team_radio,
    fetch_intervals,
    fetch_positions,
    fetch_pit_stops,
)

log = structlog.get_logger()

SESSION_MAP = {
    "Q": "Qualifying",
    "R": "Race",
    "SQ": "Sprint Qualifying",
    "S": "Sprint",
    "SS": "Sprint",
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
}

# Canonical short code for every FastF1 session name. Used so callers can pass
# either a code ("SQ") or the raw FastF1 name ("Sprint Shootout") and still get
# consistent telemetry decisions and DB session types.
NAME_TO_CODE = {
    "Qualifying": "Q",
    "Race": "R",
    "Sprint": "SS",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
}

# Sessions whose lap telemetry is worth storing (races: all laps; rest: fastest)
TELEMETRY_SESSIONS = {"Q", "SQ", "R"}


# Sessions where race-order timing (gaps, positions, pit stops) is meaningful
RACE_TIMING_SESSIONS = {"R", "SS"}


def _annotate_laps(rows: list[dict], session_obj) -> None:
    """Add lap_number to timestamped OpenF1 rows, in place.

    Lap windows are looked up per driver: a single mixed list of every driver's
    lap starts would put a backmarker's lap N start after the leader's lap N+1.
    """
    cache: dict[int, list] = {}
    for r in rows:
        drv = r["driver_number"]
        if drv not in cache:
            cache[drv] = _lap_start_times(session_obj, driver_number=drv)
        r["lap_number"] = _lap_for_timestamp(cache[drv], r["date"])


def _ingest_race_timing(session_obj, session_key: int) -> dict[str, int]:
    """OpenF1 gaps / positions / pit stops. Best-effort: never fails the ingest
    (OpenF1 has nothing before 2023, and fetchers return [] on any error)."""
    counts = {"intervals": 0, "positions": 0, "pit_stops": 0}
    try:
        intervals = fetch_intervals(session_key)
        _annotate_laps(intervals, session_obj)
        counts["intervals"] = load_session_intervals(intervals, session_key)

        positions = fetch_positions(session_key)
        _annotate_laps(positions, session_obj)
        counts["positions"] = load_position_changes(positions, session_key)

        counts["pit_stops"] = load_pit_stops(fetch_pit_stops(session_key), session_key)
    except Exception as exc:
        log.warning("race_timing.failed", session_key=session_key, error=str(exc))
    return counts


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
            "track_temp": float(last.get("TrackTemp", 0)) or None,
            "air_temp": float(last.get("AirTemp", 0)) or None,
            "humidity": float(last.get("Humidity", 0)) or None,
            "rainfall": bool(last.get("Rainfall", False)),
            "wind_speed": float(last.get("WindSpeed", 0)) or None,
        }
    except Exception as e:
        log.warning("weather.extraction_failed", error=str(e))
        return {}


# OpenF1 only has data from the 2023 season onwards.
OPENF1_FIRST_YEAR = 2023


def _openf1_fallback(year: int, gp: str, code: str) -> int | None:
    """Try the FastF1-free path when FastF1 cannot load a session.

    FastF1 fails for any session missing from its cache now that F1's static
    feed needs a login. Never raises: on any problem the caller falls through
    to the normal "not ready" handling.
    """
    try:
        from ingestion.openf1_ingest import ingest_session_openf1

        key = ingest_session_openf1(year, gp, code)
        if key is not None:
            log.info("ingest.openf1_fallback_used", session_key=key, gp=gp, session=code)
        return key
    except Exception as exc:
        log.warning("ingest.openf1_fallback_failed", gp=gp, session=code, error=str(exc))
        return None


def ingest_session(
    year: int, gp: str, session: str, skip_telemetry: bool = False
) -> int | None:
    """Ingest a single FastF1 session in-process.

    Returns the new session_key on success, or None if the ingest failed.
    Callable directly so auto_ingest does not need to shell out to `uv`.
    """
    fastf1_session = SESSION_MAP.get(session.upper(), session)
    # Canonical code whether the caller passed a code ("SQ") or a FastF1 name
    # ("Sprint Shootout", "Qualifying", ...). Falls back to the upper-cased
    # input so unknown sessions still agree between the two lookups.
    code = NAME_TO_CODE.get(fastf1_session, session.upper())

    log.info(
        "ingest.start",
        year=year,
        gp=gp,
        session=session,
        fastf1_name=fastf1_session,
    )

    try:
        session_obj = fetch_session(year, gp, fastf1_session)
        session_info = extract_session_info(session_obj)
        session_key = upsert_session(session_info)

        weather = extract_weather(session_obj)
        if weather:
            update_session_weather(session_key, **weather)
            log.info(
                "ingest.weather_stored",
                track_temp=weather.get("track_temp"),
                air_temp=weather.get("air_temp"),
            )

        drivers = extract_drivers(session_obj, session_key)
        load_drivers(drivers)

        laps = extract_laps(session_obj, session_key)
        lap_count = load_laps(laps, session_key)

        tel_count = 0
        # Q/SQ store fastest laps; races store full-lap artifacts
        if not skip_telemetry and code in TELEMETRY_SESSIONS:
            tel = extract_telemetry(
                session_obj,
                session_key,
                all_drivers=True,
                all_laps=code == "R",
            )
            tel_count = load_telemetry(tel, session_key)
        elif not skip_telemetry and code not in TELEMETRY_SESSIONS:
            log.info(
                "telemetry.skipped",
                reason="non-qualifying session — telemetry not stored by design",
                session=session,
            )

        rc_events = extract_race_control(session_obj, session_key)
        rc_count = load_race_control(rc_events, session_key)

        wx_events = extract_weather_events(session_obj, session_key)
        wx_count = load_weather_events(wx_events, session_key)

        results_count = load_session_results(
            extract_session_results(session_obj, session_key), session_key
        )
        track_status_count = load_track_status(
            extract_track_status(session_obj, session_key), session_key
        )

        timing = (
            _ingest_race_timing(session_obj, session_key)
            if code in RACE_TIMING_SESSIONS
            else {}
        )

        radio_rows = fetch_team_radio(session_key)
        for r in radio_rows:
            r["lap_number"] = _lap_for_timestamp(
                _lap_start_times(session_obj, driver_number=r["driver_number"]),
                r["date"],
            )
        radio_count = load_team_radio(radio_rows, session_key)

        log.info(
            "ingest.done",
            session_key=session_key,
            drivers=len(drivers),
            laps=lap_count,
            telemetry=tel_count,
            weather=bool(weather),
            race_control=rc_count,
            weather_events=wx_count,
            team_radio=radio_count,
            results=results_count,
            track_status=track_status_count,
            **{f"openf1_{k}": v for k, v in timing.items()},
        )
        return session_key
    except Exception as exc:
        is_data_not_loaded = (
            type(exc).__name__ == "DataNotLoadedError"
            or "DataNotLoadedError" in str(type(exc))
            or "not been loaded yet" in str(exc).lower()
        )
        if is_data_not_loaded and year >= OPENF1_FIRST_YEAR:
            key = _openf1_fallback(year, gp, code)
            if key is not None:
                return key
        if is_data_not_loaded:
            log.warning(
                "ingest.not_ready",
                year=year,
                gp=gp,
                session=session,
                reason=(
                    "FastF1 data has not been loaded yet. Either the timing data "
                    "is not published upstream, or F1's livetiming feed rejected "
                    "the request: it now returns 401 without an F1TV login, so "
                    "sessions missing from the FastF1 cache need FastF1>=3.9 and "
                    "F1_USERNAME/F1_PASSWORD (see docs/repository.md)"
                ),
            )
            raise

        log.error(
            "ingest.failed",
            year=year,
            gp=gp,
            session=session,
            error=str(exc),
            exc_info=True,
        )
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--gp", type=str, required=True)
    parser.add_argument(
        "--session", type=str, required=True, help="Q, R, SQ, S, FP1, FP2, FP3"
    )
    parser.add_argument("--skip-telemetry", action="store_true")
    args = parser.parse_args()

    try:
        ingest_session(args.year, args.gp, args.session, skip_telemetry=args.skip_telemetry)
    except Exception as exc:
        if (
            type(exc).__name__ == "DataNotLoadedError"
            or "DataNotLoadedError" in str(type(exc))
            or "not been loaded yet" in str(exc).lower()
        ):
            log.warning("ingest.cli.not_ready", error=str(exc))
            return
        raise


if __name__ == "__main__":
    main()
