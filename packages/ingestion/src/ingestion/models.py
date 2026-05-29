"""
Pydantic v2 models for FastF1 data validation.

These models sit between raw FastF1 DataFrames and the database.
Every field that could be NaN, NaT, or None gets sanitised here.
Nothing invalid ever reaches the INSERT statement.
"""
from __future__ import annotations
import math
from typing import Optional
import pandas as pd
from pydantic import BaseModel, field_validator


def _td_to_ms(val) -> Optional[float]:
    """Convert pandas Timedelta to milliseconds float. Returns None for NaT/None."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(val, 'total_seconds'):
        return round(val.total_seconds() * 1000, 3)
    return None


def _nan_to_none(val):
    """Convert NaN floats and empty strings to None."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, str) and val.strip() == '':
        return None
    return val


class SessionModel(BaseModel):
    session_key:  int
    year:         int
    gp_name:      str
    country:      Optional[str] = None
    session_type: str
    session_name: str
    date_start:   Optional[str] = None

    @field_validator('country', 'date_start', mode='before')
    @classmethod
    def clean_str(cls, v):
        return _nan_to_none(v)


class DriverModel(BaseModel):
    driver_number: int
    session_key:   int
    full_name:     str
    abbreviation:  str
    team_name:     Optional[str] = None
    team_colour:   Optional[str] = None

    @field_validator('team_name', 'team_colour', mode='before')
    @classmethod
    def clean_str(cls, v):
        return _nan_to_none(v)


class LapModel(BaseModel):
    session_key:    int
    driver_number:  int
    lap_number:     int
    lap_time_ms:    Optional[float] = None
    s1_ms:          Optional[float] = None
    s2_ms:          Optional[float] = None
    s3_ms:          Optional[float] = None
    pit_in_time_ms: Optional[float] = None
    pit_out_time_ms:Optional[float] = None
    compound:       Optional[str]   = None
    tyre_life_laps: Optional[int]   = None
    is_personal_best: bool          = False
    track_status:   Optional[str]   = None
    deleted:        bool            = False
    # Race-specific
    stint:          Optional[int]   = None
    position:       Optional[int]   = None
    fresh_tyre:     Optional[bool]  = None
    deleted_reason: Optional[str]   = None
    is_accurate:    Optional[bool]  = None
    speed_i1:       Optional[float] = None
    speed_i2:       Optional[float] = None
    speed_fl:       Optional[float] = None
    speed_st:       Optional[float] = None

    @field_validator(
        'lap_time_ms', 's1_ms', 's2_ms', 's3_ms',
        'pit_in_time_ms', 'pit_out_time_ms',
        mode='before'
    )
    @classmethod
    def timedelta_to_ms(cls, v):
        return _td_to_ms(v)

    @field_validator('compound', 'track_status', 'deleted_reason', mode='before')
    @classmethod
    def clean_str(cls, v):
        v = _nan_to_none(v)
        if v == 'None':
            return None
        return v

    @field_validator('tyre_life_laps', 'stint', 'position', mode='before')
    @classmethod
    def float_to_int(cls, v):
        v = _nan_to_none(v)
        return int(v) if v is not None else None

    @field_validator('is_personal_best', 'deleted', mode='before')
    @classmethod
    def clean_bool(cls, v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return False
        return bool(v)

    @field_validator('fresh_tyre', 'is_accurate', mode='before')
    @classmethod
    def clean_nullable_bool(cls, v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return bool(v)

    @field_validator('speed_i1', 'speed_i2', 'speed_fl', 'speed_st', mode='before')
    @classmethod
    def clean_float(cls, v):
        return _nan_to_none(v)


class TelemetryModel(BaseModel):
    session_key:   int
    driver_number: int
    lap_number:    int
    speed:         Optional[float] = None
    rpm:           Optional[int]   = None
    gear:          Optional[int]   = None
    throttle:      Optional[float] = None
    brake:         Optional[bool]  = None
    drs:           Optional[int]   = None
    distance: Optional[float] = None   # metres into lap — used for spatial overlay
    x:        Optional[float] = None   # track map coordinate
    y:        Optional[float] = None   # track map coordinate

    @field_validator('speed', 'throttle', mode='before')
    @classmethod
    def clean_float(cls, v):
        return _nan_to_none(v)

    @field_validator('rpm', 'gear', 'drs', mode='before')
    @classmethod
    def clean_int(cls, v):
        v = _nan_to_none(v)
        return int(v) if v is not None else None

    @field_validator('brake', mode='before')
    @classmethod
    def clean_bool(cls, v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return bool(v)
