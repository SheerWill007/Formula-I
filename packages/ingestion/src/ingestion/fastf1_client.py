"""
FastF1 client — fetches and normalises session data.
"""

from __future__ import annotations
import warnings
import fastf1
import pandas as pd
import structlog

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
    boundaries = all_laps[all_laps["gap"] > pd.Timedelta(minutes=5)]["LapStartTime"].tolist()

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
    fastf1.Cache.enable_cache("./fastf1_cache")
    session = fastf1.get_session(year, gp, session_type)
    load_weather = True
    session.load(telemetry=True, weather=load_weather, messages=False)
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
                }
            )
        except Exception as e:
            log.warning("driver.skip", driver=drv, error=str(e))
    return results


def extract_laps(session: fastf1.core.Session, session_key: int) -> list[dict]:
    laps = session.laps
    lap_segment_map = _segment_quali_laps(laps) if session.name in ("Qualifying", "Sprint Qualifying") else {}
    results = []
    for _, row in laps.iterrows():
        try:
            driver_num = int(row["DriverNumber"])
        except (ValueError, TypeError):
            continue
        lap_number = row.get("LapNumber")
        try:
            quali_segment = lap_segment_map.get((str(driver_num), int(lap_number))) if lap_number is not None else None
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


def extract_telemetry(
    session: fastf1.core.Session,
    session_key: int,
    all_drivers: bool = False,
) -> list[dict]:
    """
    Extract telemetry for the best qualifying lap in each segment.

    Captures: speed, rpm, gear, throttle, brake, drs, distance.
    Distance is key — it's metres around the lap, so two drivers
    can be compared at the exact same track position regardless of
    how many samples they have.

    To keep storage lean while still supporting the Q1/Q2/Q3 switcher,
    we only store up to one telemetry lap per driver per segment:
    best Q1, best Q2, best Q3.
    """
    results = []
    drivers = session.drivers if all_drivers else session.drivers[:10]
    lap_segment_map = _segment_quali_laps(session.laps)

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

            best_laps_by_segment = {}
            for _, lap in valid_laps.iterrows():
                lap_number = int(lap["LapNumber"])
                segment = lap_segment_map.get((str(drv), lap_number), 1)
                current_best = best_laps_by_segment.get(segment)
                if current_best is None or lap["LapTime"] < current_best["LapTime"]:
                    best_laps_by_segment[segment] = lap

            driver_sample_count = 0
            stored_lap_count = 0

            for segment in sorted(best_laps_by_segment):
                lap = best_laps_by_segment[segment]
                try:
                    tel = lap.get_telemetry()
                except Exception as e:
                    log.debug("telemetry.lap_failed", driver=drv, lap_number=lap.get("LapNumber"), error=str(e))
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

            log.info("telemetry.driver_done", driver=drv, laps=stored_lap_count, samples=driver_sample_count)

        except Exception as e:
            log.warning("telemetry.skip", driver=drv, error=str(e))

    log.info("telemetry.extracted", session_key=session_key, total=len(results))
    return results
