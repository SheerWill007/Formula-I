"""
Loader — writes ingested data to TimescaleDB.

All inputs are plain dicts from fastf1_client (raw FastF1 values).
This module handles all type conversion: Timedeltas to ms, NaN to None, etc.
"""

from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine, text
from ingestion.config import settings
from ingestion.headshots import upsize
import structlog

log = structlog.get_logger()

TEAM_COLOUR_FALLBACK: dict[str, str] = {
    "McLaren": "FF8000",
    "Ferrari": "E8002D",
    "Red Bull Racing": "3671C6",
    "Mercedes": "27F4D2",
    "Aston Martin": "229971",
    "Alpine": "FF87BC",
    "Williams": "64C4FF",
    "Haas": "B6BABD",
    "Kick Sauber": "52E252",
    "Sauber": "52E252",
    "RB": "6692FF",
    "Racing Bulls": "6692FF",
    "Cadillac": "C8A217",
    "Audi": "C8A217",
}


def _get_engine():
    return create_engine(settings.db_url)


def _resolve_colour(colour: Optional[str], team_name: Optional[str]) -> Optional[str]:
    if colour and colour.strip():
        return colour.lstrip("#")
    if team_name:
        if team_name in TEAM_COLOUR_FALLBACK:
            return TEAM_COLOUR_FALLBACK[team_name]
        for k, v in TEAM_COLOUR_FALLBACK.items():
            if k in team_name or team_name in k:
                return v
    return None


def _td_to_ms(val) -> Optional[float]:
    """Convert pandas Timedelta, float, or None to float ms."""
    if val is None:
        return None
    import math

    try:
        import pandas as pd

        if pd.isna(val):
            return None
    except Exception:
        pass
    try:
        return val.total_seconds() * 1000  # pandas Timedelta
    except AttributeError:
        pass
    try:
        v = float(val)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _clean_str(val) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return None if s in ("", "nan", "None", "NaT") else s


def _clean_bool(val) -> bool:
    if val is None:
        return False
    try:
        import math

        if math.isnan(float(val)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(val)


def _clean_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        import math

        f = float(val)
        return None if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return None


def _clean_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        import math

        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ── Session ──────────────────────────────────────────────────────────────────


def upsert_session(info: dict) -> int:
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO sessions (
                session_key, year, gp_name, country,
                session_type, session_name, date_start
            ) VALUES (
                :session_key, :year, :gp_name, :country,
                :session_type, :session_name, :date_start
            )
            ON CONFLICT (session_key) DO UPDATE SET
                gp_name      = EXCLUDED.gp_name,
                country      = EXCLUDED.country,
                session_type = EXCLUDED.session_type,
                session_name = EXCLUDED.session_name,
                date_start   = EXCLUDED.date_start
        """),
            info,
        )
    log.info("loader.session_upserted", session_key=info["session_key"])
    return info["session_key"]


def update_session_weather(
    session_key: int,
    track_temp: Optional[float] = None,
    air_temp: Optional[float] = None,
    humidity: Optional[float] = None,
    rainfall: Optional[bool] = None,
    wind_speed: Optional[float] = None,
) -> None:
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            UPDATE sessions SET
                track_temp_c  = :track_temp,
                air_temp_c    = :air_temp,
                humidity_pct  = :humidity,
                rainfall      = :rainfall,
                wind_speed_ms = :wind_speed
            WHERE session_key = :session_key
        """),
            {
                "session_key": session_key,
                "track_temp": track_temp,
                "air_temp": air_temp,
                "humidity": humidity,
                "rainfall": rainfall,
                "wind_speed": wind_speed,
            },
        )
    log.info("loader.weather_updated", session_key=session_key)


# ── Drivers ───────────────────────────────────────────────────────────────────


def load_drivers(drivers: list[dict]) -> None:
    if not drivers:
        return
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM drivers WHERE session_key = :sk"),
            {"sk": drivers[0]["session_key"]},
        )
        for d in drivers:
            resolved_colour = _resolve_colour(d.get("team_colour"), d.get("team_name"))
            conn.execute(
                text("""
                INSERT INTO drivers (
                    session_key, driver_number, full_name,
                    abbreviation, team_name, team_colour, headshot_url
                ) VALUES (
                    :session_key, :driver_number, :full_name,
                    :abbreviation, :team_name, :team_colour, :headshot_url
                )
            """),
                {
                    **d,
                    "team_colour": resolved_colour,
                    "headshot_url": upsize(d.get("headshot_url")),
                },
            )
    log.info("loader.drivers_loaded", count=len(drivers))


# ── Laps ──────────────────────────────────────────────────────────────────────


def load_laps(laps: list[dict], session_key: int) -> int:
    if not laps:
        return 0
    now = datetime.now(timezone.utc)
    engine = _get_engine()
    rows = []
    for lap in laps:
        rows.append(
            {
                "session_key": session_key,
                "driver_number": _clean_int(lap.get("driver_number")),
                "lap_number": _clean_int(lap.get("lap_number")),
                "lap_time_ms": _td_to_ms(lap.get("lap_time_ms")),
                "s1_ms": _td_to_ms(lap.get("s1_ms")),
                "s2_ms": _td_to_ms(lap.get("s2_ms")),
                "s3_ms": _td_to_ms(lap.get("s3_ms")),
                "compound": _clean_str(lap.get("compound")),
                "tyre_life_laps": _clean_int(lap.get("tyre_life_laps")),
                "is_personal_best": _clean_bool(lap.get("is_personal_best")),
                "pit_in_time_ms": _td_to_ms(lap.get("pit_in_time_ms")),
                "pit_out_time_ms": _td_to_ms(lap.get("pit_out_time_ms")),
                "track_status": _clean_str(lap.get("track_status")),
                "stint": _clean_int(lap.get("stint")),
                "position": _clean_int(lap.get("position")),
                "fresh_tyre": _clean_bool(lap.get("fresh_tyre")),
                "deleted_reason": _clean_str(lap.get("deleted_reason")),
                "is_accurate": _clean_bool(lap.get("is_accurate")),
                "quali_segment": _clean_int(lap.get("quali_segment")),
                "deleted": _clean_bool(lap.get("deleted")),
                "recorded_at": now,
                # Speed trap measurements — from FastF1 SpeedI1/I2/FL/ST
                # These are km/h readings at official FIA timing lines:
                # speed_i1 = intermediate 1 (end of S1 straight)
                # speed_i2 = intermediate 2 (mid-lap straight)
                # speed_fl = finish line speed (exit of final corner)
                # speed_st = official speed trap (fastest point on circuit)
                "speed_i1": _clean_float(lap.get("speed_i1")),
                "speed_i2": _clean_float(lap.get("speed_i2")),
                "speed_fl": _clean_float(lap.get("speed_fl")),
                "speed_st": _clean_float(lap.get("speed_st")),
            }
        )

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM lap_times WHERE session_key = :sk"), {"sk": session_key}
        )
        conn.execute(
            text("""
            INSERT INTO lap_times (
                session_key, driver_number, lap_number,
                lap_time_ms, s1_ms, s2_ms, s3_ms,
                compound, tyre_life_laps,
                is_personal_best, pit_in_time_ms, pit_out_time_ms,
                track_status, stint, position, fresh_tyre,
                deleted_reason, is_accurate, quali_segment, deleted,
                recorded_at,
                speed_i1, speed_i2, speed_fl, speed_st
            ) VALUES (
                :session_key, :driver_number, :lap_number,
                :lap_time_ms, :s1_ms, :s2_ms, :s3_ms,
                :compound, :tyre_life_laps,
                :is_personal_best, :pit_in_time_ms, :pit_out_time_ms,
                :track_status, :stint, :position, :fresh_tyre,
                :deleted_reason, :is_accurate, :quali_segment, :deleted,
                :recorded_at,
                :speed_i1, :speed_i2, :speed_fl, :speed_st
            )
        """),
            rows,
        )
    log.info("loader.laps_loaded", count=len(laps), session_key=session_key)
    return len(laps)


def load_race_control(events: list[dict], session_key: int) -> int:
    """Replace all the race control events for a season with the giiven list"""
    if not events:
        return 0

    engine = _get_engine()
    rows = [
        {
            "session_key": session_key,
            "category": _clean_str(ev.get("category")),
            "flag": _clean_str(ev.get("flag")),
            "scope": _clean_str(ev.get("scope")),
            "driver_number": _clean_int(ev.get("driver_number")),
            "sector": _clean_int(ev.get("sector")),
            "lap_number": _clean_int(ev.get("lap_number")),
            "message": _clean_str(ev.get("message")),
        }
        for ev in events
    ]
    with engine.begin() as conn:
        conn.execute(
            text(""" DELETE FROM race_control_events WHERE session_key = :sk """),
            {"sk": session_key},
        )

        conn.execute(
            text(
                """
                INSERT INTO race_control_events (
                    session_key, category, flag, scope, driver_number, sector, lap_number, message) 
                VALUES (
                    :session_key, :category, :flag, :scope, :driver_number, :sector, :lap_number, :message)
            """
            ),
            rows,
        )
    log.info("loader.race_control_loaded", count=len(events), session_key=session_key)
    return len(events)


def load_team_radio(rows: list[dict], session_key: int) -> int:
    """Replace all team radio clips for a session with the given list."""
    if not rows:
        return 0

    engine = _get_engine()
    clean = [
        {
            "session_key": session_key,
            "driver_number": _clean_int(r.get("driver_number")),
            "lap_number": _clean_int(r.get("lap_number")),
            "date": r.get("date"),
            "recording_url": _clean_str(r.get("recording_url")),
            "transcript": _clean_str(r.get("transcript")),
        }
        for r in rows
        if r.get("recording_url")
    ]
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM team_radio WHERE session_key = :sk"),
            {"sk": session_key},
        )
        if clean:
            conn.execute(
                text(
                    """
                    INSERT INTO team_radio (
                        session_key, driver_number, lap_number, date,
                        recording_url, transcript
                    ) VALUES (
                        :session_key, :driver_number, :lap_number, :date,
                        :recording_url, :transcript
                    )
                """
                ),
                clean,
            )
    log.info("loader.team_radio_loaded", count=len(clean), session_key=session_key)
    return len(clean)


def load_weather_events(rows: list[dict], session_key: int) -> int:
    """Replace all weather events for a session with the given list."""
    if not rows:
        return 0

    engine = _get_engine()
    clean = [
        {
            "session_key": session_key,
            "timestamp": r.get("timestamp"),
            "lap_number": _clean_int(r.get("lap_number")),
            "track_temp_c": _clean_float(r.get("track_temp_c")),
            "air_temp_c": _clean_float(r.get("air_temp_c")),
            "humidity_pct": _clean_float(r.get("humidity_pct")),
            "rainfall": _clean_bool(r.get("rainfall")),
            "wind_speed_ms": _clean_float(r.get("wind_speed_ms")),
        }
        for r in rows
        if r.get("timestamp")
    ]
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM weather_events WHERE session_key = :sk"),
            {"sk": session_key},
        )
        if clean:
            conn.execute(
                text(
                    """
                    INSERT INTO weather_events (
                        session_key, timestamp, lap_number,
                        track_temp_c, air_temp_c, humidity_pct,
                        rainfall, wind_speed_ms
                    ) VALUES (
                        :session_key, :timestamp, :lap_number,
                        :track_temp_c, :air_temp_c, :humidity_pct,
                        :rainfall, :wind_speed_ms
                    )
                """
                ),
                clean,
            )
    log.info("loader.weather_events_loaded", count=len(clean), session_key=session_key)
    return len(clean)


# ── Telemetry ─────────────────────────────────────────────────────────────────

_TEL_INSERT = """
    INSERT INTO telemetry (
        session_key, driver_number, lap_number,
        distance_m, speed_kmh, throttle_pct, brake,
        gear, rpm, drs, x_pos, y_pos,
        recorded_at, sample_order
    ) VALUES (
        :session_key, :driver_number, :lap_number,
        :distance_m, :speed_kmh, :throttle_pct, :brake,
        :gear, :rpm, :drs, :x_pos, :y_pos,
        :recorded_at, :sample_order
    )
"""


def _telemetry_storage_mode() -> str:
    mode = settings.telemetry_storage_mode.strip().lower()
    return mode if mode in {"database", "files"} else "database"


def _telemetry_storage_key(
    session_key: int, driver_number: int, lap_number: int
) -> str:
    return f"telemetry/session_{session_key}/driver_{driver_number}/lap_{lap_number}.parquet"


def _r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def _write_telemetry_artifact(
    rows: list[dict],
    session_key: int,
    driver_number: int,
    lap_number: int,
    r2_client=None,
) -> dict:
    import io
    import pyarrow as pa
    import pyarrow.parquet as pq

    storage_key = _telemetry_storage_key(session_key, driver_number, lap_number)
    table = pa.Table.from_pylist(rows)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    data = buf.getvalue()
    digest = hashlib.sha256(data).hexdigest()

    if settings.telemetry_artifact_backend == "r2":
        client = r2_client or _r2_client()
        client.put_object(
            Bucket=settings.telemetry_artifact_bucket,
            Key=storage_key,
            Body=data,
            ContentType="application/vnd.apache.parquet",
        )
        storage_backend = "r2"
    else:
        path = Path(settings.telemetry_artifact_dir) / storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        storage_backend = "local"

    return {
        "session_key": session_key,
        "driver_number": driver_number,
        "lap_number": lap_number,
        "storage_key": storage_key,
        "storage_backend": storage_backend,
        "format": "parquet",
        "sample_count": len(rows),
        "size_bytes": len(data),
        "checksum_sha256": digest,
    }


def _load_telemetry_files(rows: list[dict], session_key: int) -> int:
    from concurrent.futures import ThreadPoolExecutor

    engine = _get_engine()
    grouped: dict[tuple[int, int], list[dict]] = {}
    for i, row in enumerate(rows):
        driver_number = _clean_int(row.get("driver_number"))
        lap_number = _clean_int(row.get("lap_number"))
        if driver_number is None or lap_number is None:
            continue
        sample = {
            "distance_m": _clean_float(row.get("distance_m")),
            "speed_kmh": _clean_float(row.get("speed_kmh")),
            "throttle_pct": _clean_float(row.get("throttle_pct")),
            "brake": bool(row.get("brake", False)),
            "gear": _clean_int(row.get("gear")),
            "rpm": _clean_float(row.get("rpm")),
            "drs": _clean_int(row.get("drs")),
            "x_pos": _clean_float(row.get("x_pos")),
            "y_pos": _clean_float(row.get("y_pos")),
            "sample_order": row.get("sample_order", i),
        }
        grouped.setdefault((driver_number, lap_number), []).append(sample)

    for samples in grouped.values():
        samples.sort(
            key=lambda s: (
                s["distance_m"] is None,
                s["distance_m"] if s["distance_m"] is not None else 0,
                s["sample_order"],
            )
        )

    r2 = _r2_client() if settings.telemetry_artifact_backend == "r2" else None

    def _process_item(item):
        (driver_number, lap_number), samples = item
        return _write_telemetry_artifact(
            samples, session_key, driver_number, lap_number, r2_client=r2
        )

    workers = 16 if settings.telemetry_artifact_backend == "r2" else 4
    with ThreadPoolExecutor(max_workers=workers) as executor:
        artifacts = list(executor.map(_process_item, grouped.items()))

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM telemetry_artifacts WHERE session_key = :sk"),
            {"sk": session_key},
        )
        conn.execute(
            text("DELETE FROM telemetry WHERE session_key = :sk"), {"sk": session_key}
        )
        if artifacts:
            conn.execute(
                text("""
                INSERT INTO telemetry_artifacts (
                    session_key, driver_number, lap_number,
                    storage_key, storage_backend, format,
                    sample_count, size_bytes, checksum_sha256
                ) VALUES (
                    :session_key, :driver_number, :lap_number,
                    :storage_key, :storage_backend, :format,
                    :sample_count, :size_bytes, :checksum_sha256
                )
            """),
                artifacts,
            )

    log.info(
        "loader.telemetry_artifacts_loaded",
        artifacts=len(artifacts),
        samples=len(rows),
        session_key=session_key,
    )
    return len(rows)


def load_telemetry(rows: list[dict], session_key: int) -> int:
    if not rows:
        return 0
    if _telemetry_storage_mode() == "files":
        return _load_telemetry_files(rows, session_key)

    now = datetime.now(timezone.utc)
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM telemetry_artifacts WHERE session_key = :sk"),
            {"sk": session_key},
        )
        conn.execute(
            text("DELETE FROM telemetry WHERE session_key = :sk"), {"sk": session_key}
        )
        batch: list[dict] = []
        for i, row in enumerate(rows):
            batch.append(
                {
                    "session_key": session_key,
                    "driver_number": row.get("driver_number"),
                    "lap_number": row.get("lap_number"),
                    "distance_m": _clean_float(row.get("distance_m")),
                    "speed_kmh": _clean_float(row.get("speed_kmh")),
                    "throttle_pct": _clean_float(row.get("throttle_pct")),
                    "brake": bool(row.get("brake", False)),
                    "gear": _clean_int(row.get("gear")),
                    "rpm": _clean_float(row.get("rpm")),
                    "drs": _clean_int(row.get("drs")),
                    "x_pos": _clean_float(row.get("x_pos")),
                    "y_pos": _clean_float(row.get("y_pos")),
                    "recorded_at": row.get("recorded_at") or now,
                    "sample_order": row.get("sample_order", i),
                }
            )
            if len(batch) >= 1000:
                conn.execute(text(_TEL_INSERT), batch)
                batch = []
        if batch:
            conn.execute(text(_TEL_INSERT), batch)
    log.info("loader.telemetry_loaded", count=len(rows), session_key=session_key)
    return len(rows)


# ── Results, track status, OpenF1 timing, Jolpica history ────────────────────


def _replace_for_session(
    table: str, session_key: int, insert_sql: str, rows: list[dict]
) -> int:
    """Delete a session's rows in ``table`` and insert ``rows`` atomically.

    ``table`` is only ever a hard-coded literal from this module (never user
    input), so the f-string is safe; all values stay bound parameters.
    """
    if not rows:
        return 0
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM {table} WHERE session_key = :sk"), {"sk": session_key}
        )
        for i in range(0, len(rows), 2000):
            conn.execute(text(insert_sql), rows[i : i + 2000])
    log.info("loader.rows_loaded", table=table, count=len(rows), session_key=session_key)
    return len(rows)


def load_session_results(rows: list[dict], session_key: int) -> int:
    clean = [
        {
            "session_key": session_key,
            "driver_number": _clean_int(r.get("driver_number")),
            "abbreviation": _clean_str(r.get("abbreviation")),
            "team_name": _clean_str(r.get("team_name")),
            "grid_position": _clean_int(r.get("grid_position")),
            "position": _clean_int(r.get("position")),
            "classified_position": _clean_str(r.get("classified_position")),
            "status": _clean_str(r.get("status")),
            "points": _clean_float(r.get("points")),
            "laps_completed": _clean_int(r.get("laps_completed")),
            "race_time_ms": _clean_float(r.get("race_time_ms")),
            "q1_ms": _clean_float(r.get("q1_ms")),
            "q2_ms": _clean_float(r.get("q2_ms")),
            "q3_ms": _clean_float(r.get("q3_ms")),
        }
        for r in rows
        if _clean_int(r.get("driver_number")) is not None
    ]
    return _replace_for_session(
        "session_results",
        session_key,
        """
        INSERT INTO session_results (
            session_key, driver_number, abbreviation, team_name, grid_position,
            position, classified_position, status, points, laps_completed,
            race_time_ms, q1_ms, q2_ms, q3_ms
        ) VALUES (
            :session_key, :driver_number, :abbreviation, :team_name, :grid_position,
            :position, :classified_position, :status, :points, :laps_completed,
            :race_time_ms, :q1_ms, :q2_ms, :q3_ms
        )
        """,
        clean,
    )


def load_track_status(rows: list[dict], session_key: int) -> int:
    clean = [
        {
            "session_key": session_key,
            "status_code": _clean_str(r.get("status_code")),
            "status_label": _clean_str(r.get("status_label")) or "Unknown",
            "start_ms": _clean_float(r.get("start_ms")),
            "end_ms": _clean_float(r.get("end_ms")),
            "start_lap": _clean_int(r.get("start_lap")),
            "end_lap": _clean_int(r.get("end_lap")),
        }
        for r in rows
        if _clean_str(r.get("status_code")) and _clean_float(r.get("start_ms")) is not None
    ]
    return _replace_for_session(
        "track_status_periods",
        session_key,
        """
        INSERT INTO track_status_periods (
            session_key, status_code, status_label, start_ms, end_ms,
            start_lap, end_lap
        ) VALUES (
            :session_key, :status_code, :status_label, :start_ms, :end_ms,
            :start_lap, :end_lap
        )
        """,
        clean,
    )


def load_session_intervals(rows: list[dict], session_key: int) -> int:
    clean = [
        {
            "session_key": session_key,
            "driver_number": _clean_int(r.get("driver_number")),
            "date": r.get("date"),
            "lap_number": _clean_int(r.get("lap_number")),
            "gap_to_leader_s": _clean_float(r.get("gap_to_leader_s")),
            "interval_s": _clean_float(r.get("interval_s")),
            "gap_to_leader_raw": _clean_str(r.get("gap_to_leader_raw")),
            "interval_raw": _clean_str(r.get("interval_raw")),
        }
        for r in rows
        if r.get("date") and _clean_int(r.get("driver_number")) is not None
    ]
    return _replace_for_session(
        "session_intervals",
        session_key,
        """
        INSERT INTO session_intervals (
            session_key, driver_number, date, lap_number, gap_to_leader_s,
            interval_s, gap_to_leader_raw, interval_raw
        ) VALUES (
            :session_key, :driver_number, :date, :lap_number, :gap_to_leader_s,
            :interval_s, :gap_to_leader_raw, :interval_raw
        )
        """,
        clean,
    )


def load_position_changes(rows: list[dict], session_key: int) -> int:
    clean = [
        {
            "session_key": session_key,
            "driver_number": _clean_int(r.get("driver_number")),
            "date": r.get("date"),
            "lap_number": _clean_int(r.get("lap_number")),
            "position": _clean_int(r.get("position")),
        }
        for r in rows
        if r.get("date")
        and _clean_int(r.get("driver_number")) is not None
        and _clean_int(r.get("position")) is not None
    ]
    return _replace_for_session(
        "position_changes",
        session_key,
        """
        INSERT INTO position_changes (
            session_key, driver_number, date, lap_number, position
        ) VALUES (
            :session_key, :driver_number, :date, :lap_number, :position
        )
        """,
        clean,
    )


def load_pit_stops(rows: list[dict], session_key: int) -> int:
    # (session, driver, lap) is unique; OpenF1 occasionally repeats a row.
    seen: dict[tuple, dict] = {}
    for r in rows:
        driver, lap = _clean_int(r.get("driver_number")), _clean_int(r.get("lap_number"))
        if driver is None or lap is None:
            continue
        seen[(driver, lap)] = {
            "session_key": session_key,
            "driver_number": driver,
            "lap_number": lap,
            "date": r.get("date"),
            "pit_duration_s": _clean_float(r.get("pit_duration_s")),
        }
    return _replace_for_session(
        "pit_stops",
        session_key,
        """
        INSERT INTO pit_stops (
            session_key, driver_number, lap_number, date, pit_duration_s
        ) VALUES (
            :session_key, :driver_number, :lap_number, :date, :pit_duration_s
        )
        """,
        list(seen.values()),
    )


def load_historical_results(rows: list[dict]) -> int:
    """Upsert Jolpica rows. Idempotent: safe to re-run for the same years."""
    if not rows:
        return 0
    engine = _get_engine()
    with engine.begin() as conn:
        for i in range(0, len(rows), 1000):
            conn.execute(
                text(
                    """
                    INSERT INTO historical_results (
                        year, round, kind, race_name, circuit_id, circuit_name,
                        country, race_date, driver_id, driver_code, driver_name,
                        constructor_id, constructor_name, grid, position,
                        position_text, points, laps, status, q1, q2, q3
                    ) VALUES (
                        :year, :round, :kind, :race_name, :circuit_id, :circuit_name,
                        :country, :race_date, :driver_id, :driver_code, :driver_name,
                        :constructor_id, :constructor_name, :grid, :position,
                        :position_text, :points, :laps, :status, :q1, :q2, :q3
                    )
                    ON CONFLICT (year, round, kind, driver_id) DO UPDATE SET
                        race_name = EXCLUDED.race_name,
                        circuit_id = EXCLUDED.circuit_id,
                        circuit_name = EXCLUDED.circuit_name,
                        country = EXCLUDED.country,
                        race_date = EXCLUDED.race_date,
                        driver_code = EXCLUDED.driver_code,
                        driver_name = EXCLUDED.driver_name,
                        constructor_id = EXCLUDED.constructor_id,
                        constructor_name = EXCLUDED.constructor_name,
                        grid = EXCLUDED.grid,
                        position = EXCLUDED.position,
                        position_text = EXCLUDED.position_text,
                        points = EXCLUDED.points,
                        laps = EXCLUDED.laps,
                        status = EXCLUDED.status,
                        q1 = EXCLUDED.q1, q2 = EXCLUDED.q2, q3 = EXCLUDED.q3
                    """
                ),
                rows[i : i + 1000],
            )
    log.info("loader.historical_results_loaded", count=len(rows))
    return len(rows)
