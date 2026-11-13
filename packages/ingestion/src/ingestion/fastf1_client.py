"""
FastF1 client — fetches and normalises session data.
"""

from __future__ import annotations
import math
import warnings
from typing import TYPE_CHECKING

import pandas as pd
import structlog

if TYPE_CHECKING:
    import fastf1

warnings.filterwarnings("ignore")
log = structlog.get_logger()


def _segment_quali_laps(laps):
    """
    Annotate qualifying laps with segment numbers:
    1 = Q1, 2 = Q2, 3 = Q3.
    """
    if laps is None or laps.empty or "LapStartTime" not in laps:
        return {}

    all_laps = laps[["DriverNumber", "LapNumber", "LapStartTime"]].copy()
    all_laps = all_laps.dropna(subset=["LapStartTime", "LapNumber", "DriverNumber"])
    if all_laps.empty:
        return {}

    all_laps = all_laps.sort_values("LapStartTime")
    all_laps["gap"] = all_laps["LapStartTime"].diff()
    boundaries = all_laps[all_laps["gap"] > pd.Timedelta(minutes=5)][
        "LapStartTime"
    ].tolist()

    def assign_segment(t):
        if len(boundaries) == 0:
            return 1
        if t < boundaries[0]:
            return 1
        if len(boundaries) < 2 or t < boundaries[1]:
            return 2
        return 3

    all_laps["segment"] = all_laps["LapStartTime"].apply(assign_segment)
    return {
        (str(row["DriverNumber"]), int(row["LapNumber"])): int(row["segment"])
        for _, row in all_laps.iterrows()
    }


def fetch_session(year: int, gp: str, session_type: str) -> fastf1.core.Session:
    import fastf1  # heavy — pulled in lazily; ingestion workers only

    import os

    cache_dir = os.environ.get("FASTF1_CACHE_DIR", "./fastf1_cache")
    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)
    session = fastf1.get_session(year, gp, session_type)
    load_weather = True
    session.load(telemetry=True, weather=load_weather, messages=True, livedata=None)
    log.info(
        "session.loaded",
        year=year,
        gp=gp,
        type=session_type,
        drivers=len(session.drivers),
    )
    return session


def extract_session_info(session: fastf1.core.Session) -> dict:
    event = session.event
    key = session.session_info.get("Key")
    if not key:
        import hashlib

        key = int(
            hashlib.md5(f"{event['EventName']}{session.name}".encode()).hexdigest()[:8],
            16,
        )
    return {
        "session_key": int(key),
        "year": int(event["EventDate"].year),
        "gp_name": event["EventName"],
        "country": event.get("Country", None),
        "session_type": {
            "Qualifying": "Q",
            "Race": "R",
            "Sprint": "SS",
            "Sprint Qualifying": "SQ",
            "Sprint Shootout": "SQ",
            "Practice 1": "FP1",
            "Practice 2": "FP2",
            "Practice 3": "FP3",
        }.get(session.name, session.name[:2]),
        "session_name": session.name,
        "date_start": str(event["EventDate"]),
    }


def extract_drivers(session: fastf1.core.Session, session_key: int) -> list[dict]:
    results = []
    for drv in session.drivers:
        try:
            info = session.get_driver(drv)
            results.append(
                {
                    "driver_number": int(drv),
                    "session_key": session_key,
                    "full_name": info.get("FullName", info.get("BroadcastName", drv)),
                    "abbreviation": info.get("Abbreviation", drv),
                    "team_name": info.get("TeamName", None),
                    "team_colour": info.get("TeamColour", None),
                    "headshot_url": info.get("HeadshotUrl") or None,
                }
            )
        except Exception as e:
            log.warning("driver.skip", driver=drv, error=str(e))
    return results


def extract_laps(session: fastf1.core.Session, session_key: int) -> list[dict]:
    laps = session.laps
    lap_segment_map = (
        _segment_quali_laps(laps)
        if session.name in ("Qualifying", "Sprint Qualifying")
        else {}
    )
    results = []
    for _, row in laps.iterrows():
        try:
            driver_num = int(row["DriverNumber"])
        except (ValueError, TypeError):
            continue
        lap_number = row.get("LapNumber")
        try:
            quali_segment = (
                lap_segment_map.get((str(driver_num), int(lap_number)))
                if lap_number is not None
                else None
            )
        except (TypeError, ValueError):
            quali_segment = None
        results.append(
            {
                "session_key": session_key,
                "driver_number": driver_num,
                "lap_number": lap_number,
                "lap_time_ms": row.get("LapTime"),
                "pit_in_time_ms": row.get("PitInTime"),
                "pit_out_time_ms": row.get("PitOutTime"),
                "s1_ms": row.get("Sector1Time"),
                "s2_ms": row.get("Sector2Time"),
                "s3_ms": row.get("Sector3Time"),
                "compound": row.get("Compound"),
                "tyre_life_laps": row.get("TyreLife"),
                "is_personal_best": row.get("IsPersonalBest", False),
                "track_status": row.get("TrackStatus"),
                "deleted": row.get("Deleted"),
                "stint": row.get("Stint"),
                "position": row.get("Position"),
                "fresh_tyre": row.get("FreshTyre"),
                "deleted_reason": row.get("DeletedReason"),
                "is_accurate": row.get("IsAccurate"),
                "speed_i1": row.get("SpeedI1"),
                "speed_i2": row.get("SpeedI2"),
                "speed_fl": row.get("SpeedFL"),
                "speed_st": row.get("SpeedST"),
                "quali_segment": quali_segment,
            }
        )
    log.info("laps.extracted", session_key=session_key, count=len(results))
    return results


def extract_race_control(session: fastf1.core.Session, session_key: int) -> list[dict]:
    """Extract the race control messages (safety car, VSC, yellow/red flags, DRS) into a list of events dicts for storage"""
    try:
        rc = session.race_control_messages
    except Exception as e:
        log.warning("race_control.extract_failed", error=str(e))
        return []

    if rc is None or rc.empty:
        log.info("race_control.empty", session_key=session_key)
        return []

    results = []
    for _, row in rc.iterrows():
        results.append(
            {
                "session_key": session_key,
                "category": _clean(row.get("Category")),
                "flag": _clean(row.get("Flag")),
                "scope": _clean(row.get("Scope")),
                "driver_number": _to_int(row.get("DriverNumber")),
                "sector": _to_int(row.get("Sector")),
                "lap_number": _to_int(row.get("LapNumber")),
                "message": _clean(row.get("Message")),
            }
        )
    log.info("race_control.extracted", session_key=session_key, count=len(results))
    return results


def _lap_start_times(session, driver_number=None):
    """
    Build a sorted list of (lap_number, start) covering the session's recorded
    laps (optionally one driver). The `start` value is the absolute lock-step ON
    LapStartDate when available, otherwise it falls back to the session-relative
    LapStartTime clock. Used to derive a lap_number from a timestamp (team radio,
    weather). Returns [] when lap data is absent.
    """
    laps = session.laps
    if laps is None or laps.empty:
        return []
    has_date = "LapStartDate" in laps and laps["LapStartDate"].notna().any()
    col = "LapStartDate" if has_date else "LapStartTime"
    if col not in laps:
        return []
    rows = []
    for _, row in laps.iterrows():
        drv = row.get("DriverNumber")
        try:
            drv = int(drv)
        except (TypeError, ValueError):
            continue
        if driver_number is not None and drv != driver_number:
            continue
        start = row.get(col)
        lap = row.get("LapNumber")
        try:
            lap = int(lap)
        except (TypeError, ValueError):
            continue
        if start is None or lap is None:
            continue
        try:
            if pd.isna(start):
                continue
        except Exception:
            pass
        rows.append((int(lap), start))
    rows.sort(key=lambda r: r[1])
    return rows


def _lap_for_timestamp(lap_starts: list[tuple[int, object]], ts) -> int | None:
    """Return the lap_number whose [start, next_start) window contains ts."""
    if not lap_starts or ts is None:
        return None
    try:
        if isinstance(ts, str):
            ts = pd.Timestamp(ts)
    except (ValueError, TypeError):
        return None
    if not lap_starts:
        return None

    # LapStartDate from FastF1 is usually tz-naive while our incoming timestamps
    # (OpenF1 `date`, weather `t0_date + Time`) are tz-aware UTC. Normalise the
    # incoming ts to the same timezone convention as the lap-start reference so
    # the comparison doesn't throw a naive/aware mismatch.
    ref = lap_starts[0][1]
    if isinstance(ts, pd.Timestamp) and isinstance(ref, pd.Timestamp):
        if ref.tzinfo is None and ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        elif ref.tzinfo is not None and ts.tzinfo is None:
            ts = ts.tz_localize(ref.tzinfo)

    best_lap = None
    for lap, start in lap_starts:
        try:
            if pd.isna(start):
                continue
            if start <= ts:
                best_lap = lap
            else:
                break
        except (TypeError, ValueError):
            # clock mismatch (absolute LapStartDate vs relative LapStartTime, or
            # vice versa) — the two sources aren't on the same timebase
            return None
    return best_lap


def extract_weather_events(
    session: fastf1.core.Session, session_key: int
) -> list[dict]:
    """
    Extract every weather sample from session.weather_data into event rows,
    deriving the lap_number each sample belongs to from lap start times.
    This powers "Was it raining when he pitted?" style queries.
    """
    try:
        wx = session.weather_data
    except Exception as e:
        log.warning("weather_events.extract_failed", error=str(e))
        return []
    if wx is None or wx.empty:
        return []

    lap_starts = _lap_start_times(session)

    results = []
    for _, row in wx.iterrows():
        # weather_data is indexed by a RangeIndex with a t0-relative `Time`
        # column (timedelta since session start). Lap starts are absolute
        # (`LapStartDate = LapStartTime + t0`) when telemetry was loaded, so we
        # must convert weather Time to the same absolute clock via session.t0_date.
        t_rel = row.get("Time")
        ts: object | None = None
        lap_number: int | None = None
        if t_rel is not None:
            relative_clock = not lap_starts or not isinstance(
                lap_starts[0][1], pd.Timestamp
            )
            if not relative_clock:
                try:
                    t0 = session.t0_date
                    ts = pd.Timestamp(t0) + pd.Timedelta(t_rel)
                    lap_number = _lap_for_timestamp(lap_starts, ts)
                except Exception:
                    relative_clock = True
            if relative_clock:
                ts = t_rel
                lap_number = _lap_for_timestamp(lap_starts, ts)
        rainfall = row.get("RainFull", row.get("Rainfall", False))
        results.append(
            {
                "session_key": session_key,
                "timestamp": str(ts) if ts is not None else None,
                "lap_number": lap_number,
                "track_temp_c": _to_float(row.get("TrackTemp")),
                "air_temp_c": _to_float(row.get("AirTemp")),
                "humidity_pct": _to_float(row.get("Humidity")),
                "rainfall": bool(rainfall),
                "wind_speed_ms": _to_float(row.get("WindSpeed")),
            }
        )
    log.info("weather_events.extracted", session_key=session_key, count=len(results))
    return results


def _clean(val):
    """sanitise a string field (NaN → None)"""
    if (
        val is None
        or (isinstance(val, float) and math.isnan(val))
        or str(val).strip() == ""
    ):
        return None
    return str(val).strip()


def _to_int(val):
    """sanitise an int field (NaN/empty → None)"""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _to_float(val):
    """sanitise a float field (NaN/empty → None)"""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def extract_telemetry(
    session: fastf1.core.Session,
    session_key: int,
    all_drivers: bool = False,
    all_laps: bool = False,
) -> list[dict]:
    """
    Extract telemetry samples for a session.

    Captures: speed, rpm, gear, throttle, brake, drs, distance.
    Distance is key — it's metres around the lap, so two drivers
    can be compared at the exact same track position regardless of
    how many samples they have.

    Qualifying stores up to one telemetry lap per driver per segment:
    best Q1, best Q2, best Q3.

    Race ingestion can pass all_laps=True so the agent can compute windows
    around any pit stop without guessing from partial traces.
    """
    results = []
    drivers = session.drivers if all_drivers else session.drivers[:10]
    is_qualifying = session.name in ("Qualifying", "Sprint Qualifying")
    lap_segment_map = _segment_quali_laps(session.laps) if is_qualifying else {}

    for drv in drivers:
        try:
            driver_laps = session.laps.pick_drivers(drv)
            if driver_laps is None or driver_laps.empty:
                log.debug("telemetry.no_laps", driver=drv)
                continue

            valid_laps = driver_laps[
                driver_laps["LapTime"].notna()
                & driver_laps["LapNumber"].notna()
                & (~driver_laps["Deleted"].fillna(False))
            ]

            if valid_laps.empty:
                log.debug("telemetry.no_valid_laps", driver=drv)
                continue

            if all_laps:
                laps_to_store = list(valid_laps.sort_values("LapNumber").iterrows())
            else:
                best_laps_by_segment = {}
                for _, lap in valid_laps.iterrows():
                    lap_number = int(lap["LapNumber"])
                    segment = lap_segment_map.get((str(drv), lap_number), 1)
                    current_best = best_laps_by_segment.get(segment)
                    if current_best is None or lap["LapTime"] < current_best["LapTime"]:
                        best_laps_by_segment[segment] = lap
                laps_to_store = [
                    (None, best_laps_by_segment[segment])
                    for segment in sorted(best_laps_by_segment)
                ]

            driver_sample_count = 0
            stored_lap_count = 0

            for _, lap in laps_to_store:
                try:
                    tel = lap.get_telemetry()
                except Exception as e:
                    log.debug(
                        "telemetry.lap_failed",
                        driver=drv,
                        lap_number=lap.get("LapNumber"),
                        error=str(e),
                    )
                    continue

                if tel is None or tel.empty:
                    continue

                lap_number = int(lap["LapNumber"])
                stored_lap_count += 1

                for _, row in tel.iterrows():
                    results.append(
                        {
                            "session_key": session_key,
                            "driver_number": int(drv),
                            "lap_number": lap_number,
                            "speed_kmh": row.get("Speed"),
                            "rpm": row.get("RPM"),
                            "gear": row.get("nGear"),
                            "throttle_pct": row.get("Throttle"),
                            "brake": row.get("Brake"),
                            "drs": row.get("DRS"),
                            "distance_m": row.get("Distance"),
                            "x_pos": row.get("X"),
                            "y_pos": row.get("Y"),
                        }
                    )
                driver_sample_count += len(tel)

            log.info(
                "telemetry.driver_done",
                driver=drv,
                laps=stored_lap_count,
                samples=driver_sample_count,
            )

        except Exception as e:
            log.warning("telemetry.skip", driver=drv, error=str(e))

    log.info("telemetry.extracted", session_key=session_key, total=len(results))
    return results


# ── Session results & track status ───────────────────────────────────────────

TRACK_STATUS_LABELS = {
    "1": "AllClear",
    "2": "Yellow",
    "3": "Unknown",
    "4": "SafetyCar",
    "5": "Red",
    "6": "VirtualSafetyCar",
    "7": "VSCEnding",
}


def _timedelta_ms(val) -> float | None:
    """Timedelta -> ms; NaT/None/garbage -> None."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
        return float(pd.Timedelta(val).total_seconds() * 1000)
    except (TypeError, ValueError):
        return None


def extract_session_results(session: fastf1.core.Session, session_key: int) -> list[dict]:
    """Final classification: grid, finish, points, status and Q1/Q2/Q3 times.

    These are the labels for race-prediction training and the retirement model.
    Columns missing in older FastF1 versions are simply None.
    """
    try:
        res = session.results
    except Exception as e:
        log.warning("results.extract_failed", error=str(e))
        return []
    if res is None or res.empty:
        log.info("results.empty", session_key=session_key)
        return []

    rows = []
    for _, row in res.iterrows():
        driver_number = _to_int(row.get("DriverNumber"))
        if driver_number is None:
            continue
        rows.append(
            {
                "session_key": session_key,
                "driver_number": driver_number,
                "abbreviation": _clean(row.get("Abbreviation")),
                "team_name": _clean(row.get("TeamName")),
                "grid_position": _to_int(row.get("GridPosition")),
                "position": _to_int(row.get("Position")),
                "classified_position": _clean(row.get("ClassifiedPosition")),
                "status": _clean(row.get("Status")),
                "points": _to_float(row.get("Points")),
                "laps_completed": _to_int(row.get("Laps")),
                "race_time_ms": _timedelta_ms(row.get("Time")),
                "q1_ms": _timedelta_ms(row.get("Q1")),
                "q2_ms": _timedelta_ms(row.get("Q2")),
                "q3_ms": _timedelta_ms(row.get("Q3")),
            }
        )
    log.info("results.extracted", session_key=session_key, count=len(rows))
    return rows


def _relative_lap_starts(session) -> list[tuple[int, pd.Timedelta]]:
    """(lap_number, earliest LapStartTime across drivers), sorted by time.

    Uses the session-relative ``LapStartTime`` clock, which is the same clock
    ``track_status`` uses -- so no tz / absolute-vs-relative conversion needed.
    """
    laps = session.laps
    if laps is None or laps.empty or "LapStartTime" not in laps:
        return []
    sub = laps[["LapNumber", "LapStartTime"]].dropna()
    if sub.empty:
        return []
    earliest = sub.groupby("LapNumber")["LapStartTime"].min().sort_values()
    return [(int(lap), start) for lap, start in earliest.items()]


def _lap_at(lap_starts: list[tuple[int, pd.Timedelta]], t: pd.Timedelta) -> int | None:
    best = None
    for lap, start in lap_starts:
        if start <= t:
            best = lap
        else:
            break
    return best


def extract_track_status(session: fastf1.core.Session, session_key: int) -> list[dict]:
    """Turn FastF1's status change log into closed [start, end) periods.

    ``session.track_status`` has one row per *change* (Time, Status, Message).
    Each row opens a period that ends where the next one starts; the last
    period has end_ms=None. Needed to simulate safety-car probability.
    """
    try:
        ts = session.track_status
    except Exception as e:
        log.warning("track_status.extract_failed", error=str(e))
        return []
    if ts is None or ts.empty:
        log.info("track_status.empty", session_key=session_key)
        return []

    ts = ts.sort_values("Time").reset_index(drop=True)
    lap_starts = _relative_lap_starts(session)
    periods = []
    for i, row in ts.iterrows():
        start = pd.Timedelta(row["Time"])
        end = pd.Timedelta(ts.loc[i + 1, "Time"]) if i + 1 < len(ts) else None
        code = str(row["Status"]).strip()
        periods.append(
            {
                "session_key": session_key,
                "status_code": code,
                "status_label": TRACK_STATUS_LABELS.get(code, "Unknown"),
                "start_ms": start.total_seconds() * 1000,
                "end_ms": end.total_seconds() * 1000 if end is not None else None,
                "start_lap": _lap_at(lap_starts, start),
                "end_lap": _lap_at(lap_starts, end) if end is not None else None,
            }
        )
    log.info("track_status.extracted", session_key=session_key, count=len(periods))
    return periods
