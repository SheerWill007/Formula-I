"""
Loader — writes ingested data to TimescaleDB.

All inputs are plain dicts from fastf1_client (raw FastF1 values).
This module handles all type conversion: Timedeltas to ms, NaN to None, etc.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import create_engine, text
from ingestion.config import settings
import structlog

log = structlog.get_logger()

TEAM_COLOUR_FALLBACK: dict[str, str] = {
    'McLaren':          'FF8000',
    'Ferrari':          'E8002D',
    'Red Bull Racing':  '3671C6',
    'Mercedes':         '27F4D2',
    'Aston Martin':     '229971',
    'Alpine':           'FF87BC',
    'Williams':         '64C4FF',
    'Haas':             'B6BABD',
    'Kick Sauber':      '52E252',
    'Sauber':           '52E252',
    'RB':               '6692FF',
    'Racing Bulls':     '6692FF',
    'Cadillac':         'C8A217',
    'Audi':             'C8A217',
}


def _get_engine():
    url = settings.database_url.replace("postgres://", "postgresql+psycopg://").replace("postgresql://", "postgresql+psycopg://")
    return create_engine(url)


def _resolve_colour(colour: Optional[str], team_name: Optional[str]) -> Optional[str]:
    if colour and colour.strip():
        return colour.lstrip('#')
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
    return None if s in ('', 'nan', 'None', 'NaT') else s


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
        conn.execute(text("""
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
        """), info)
    log.info("loader.session_upserted", session_key=info['session_key'])
    return info['session_key']


def update_session_weather(
    session_key: int,
    track_temp:  Optional[float] = None,
    air_temp:    Optional[float] = None,
    humidity:    Optional[float] = None,
    rainfall:    Optional[bool]  = None,
    wind_speed:  Optional[float] = None,
) -> None:
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE sessions SET
                track_temp_c  = :track_temp,
                air_temp_c    = :air_temp,
                humidity_pct  = :humidity,
                rainfall      = :rainfall,
                wind_speed_ms = :wind_speed
            WHERE session_key = :session_key
        """), {
            'session_key': session_key,
            'track_temp':  track_temp,
            'air_temp':    air_temp,
            'humidity':    humidity,
            'rainfall':    rainfall,
            'wind_speed':  wind_speed,
        })
    log.info("loader.weather_updated", session_key=session_key)


# ── Drivers ───────────────────────────────────────────────────────────────────

def load_drivers(drivers: list[dict]) -> None:
    if not drivers:
        return
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM drivers WHERE session_key = :sk"),
            {"sk": drivers[0]['session_key']}
        )
        for d in drivers:
            resolved_colour = _resolve_colour(d.get('team_colour'), d.get('team_name'))
            conn.execute(text("""
                INSERT INTO drivers (
                    session_key, driver_number, full_name,
                    abbreviation, team_name, team_colour
                ) VALUES (
                    :session_key, :driver_number, :full_name,
                    :abbreviation, :team_name, :team_colour
                )
            """), {**d, 'team_colour': resolved_colour})
    log.info("loader.drivers_loaded", count=len(drivers))


# ── Laps ──────────────────────────────────────────────────────────────────────

def load_laps(laps: list[dict], session_key: int) -> int:
    if not laps:
        return 0
    now = datetime.now(timezone.utc)
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM lap_times WHERE session_key = :sk"),
            {"sk": session_key}
        )
        for lap in laps:
            row = {
                'session_key':      session_key,
                'driver_number':    _clean_int(lap.get('driver_number')),
                'lap_number':       _clean_int(lap.get('lap_number')),
                'lap_time_ms':      _td_to_ms(lap.get('lap_time_ms')),
                's1_ms':            _td_to_ms(lap.get('s1_ms')),
                's2_ms':            _td_to_ms(lap.get('s2_ms')),
                's3_ms':            _td_to_ms(lap.get('s3_ms')),
                'compound':         _clean_str(lap.get('compound')),
                'tyre_life_laps':   _clean_int(lap.get('tyre_life_laps')),
                'is_personal_best': _clean_bool(lap.get('is_personal_best')),
                'track_status':     _clean_str(lap.get('track_status')),
                'position':         _clean_int(lap.get('position')),
                'quali_segment':    _clean_int(lap.get('quali_segment')),
                'deleted':          _clean_bool(lap.get('deleted')),
                'recorded_at':      now,
                # Speed trap measurements — from FastF1 SpeedI1/I2/FL/ST
                # These are km/h readings at official FIA timing lines:
                # speed_i1 = intermediate 1 (end of S1 straight)
                # speed_i2 = intermediate 2 (mid-lap straight)
                # speed_fl = finish line speed (exit of final corner)
                # speed_st = official speed trap (fastest point on circuit)
                'speed_i1':         _clean_float(lap.get('speed_i1')),
                'speed_i2':         _clean_float(lap.get('speed_i2')),
                'speed_fl':         _clean_float(lap.get('speed_fl')),
                'speed_st':         _clean_float(lap.get('speed_st')),
            }
            conn.execute(text("""
                INSERT INTO lap_times (
                    session_key, driver_number, lap_number,
                    lap_time_ms, s1_ms, s2_ms, s3_ms,
                    compound, tyre_life_laps,
                    is_personal_best, track_status, position, quali_segment, deleted,
                    recorded_at,
                    speed_i1, speed_i2, speed_fl, speed_st
                ) VALUES (
                    :session_key, :driver_number, :lap_number,
                    :lap_time_ms, :s1_ms, :s2_ms, :s3_ms,
                    :compound, :tyre_life_laps,
                    :is_personal_best, :track_status, :position, :quali_segment, :deleted,
                    :recorded_at,
                    :speed_i1, :speed_i2, :speed_fl, :speed_st
                )
            """), row)
    log.info("loader.laps_loaded", count=len(laps), session_key=session_key)
    return len(laps)


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


def load_telemetry(rows: list[dict], session_key: int) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc)
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM telemetry WHERE session_key = :sk"),
            {"sk": session_key}
        )
        batch: list[dict] = []
        for i, row in enumerate(rows):
            batch.append({
                'session_key':   session_key,
                'driver_number': row.get('driver_number'),
                'lap_number':    row.get('lap_number'),
                'distance_m':    _clean_float(row.get('distance_m')),
                'speed_kmh':     _clean_float(row.get('speed_kmh')),
                'throttle_pct':  _clean_float(row.get('throttle_pct')),
                'brake':         bool(row.get('brake', False)),
                'gear':          _clean_int(row.get('gear')),
                'rpm':           _clean_float(row.get('rpm')),
                'drs':           _clean_int(row.get('drs')),
                'x_pos':         _clean_float(row.get('x_pos')),
                'y_pos':         _clean_float(row.get('y_pos')),
                'recorded_at':   row.get('recorded_at') or now,
                'sample_order':  row.get('sample_order', i),
            })
            if len(batch) >= 1000:
                conn.execute(text(_TEL_INSERT), batch)
                batch = []
        if batch:
            conn.execute(text(_TEL_INSERT), batch)
    log.info("loader.telemetry_loaded", count=len(rows), session_key=session_key)
    return len(rows)
