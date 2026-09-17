"""
Session Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class DriverSchema(BaseModel):
    """Driver schema."""
    driver_number: int
    full_name: str
    abbreviation: Optional[str] = None
    team_name: Optional[str] = None
    team_colour: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseModel):
    """Session response schema."""
    session_key: int
    year: int
    gp_name: str
    country: Optional[str] = None
    session_type: str
    session_name: str
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    track_temp_c: Optional[float] = None
    air_temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    rainfall: Optional[bool] = None
    wind_speed_ms: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm(cls, obj):
        """Create from ORM model."""
        return cls.model_validate(obj)


class SessionDetailResponse(SessionResponse):
    """Session detail response with drivers."""
    drivers: List[DriverSchema] = []

    @classmethod
    def from_orm_with_drivers(cls, session, drivers):
        """Create from session ORM model with separate driver list."""
        data = {
            "session_key": session.session_key,
            "year": session.year,
            "gp_name": session.gp_name,
            "country": session.country,
            "session_type": session.session_type,
            "session_name": session.session_name,
            "date_start": session.date_start,
            "date_end": session.date_end,
            "track_temp_c": session.track_temp_c,
            "air_temp_c": session.air_temp_c,
            "humidity_pct": session.humidity_pct,
            "rainfall": session.rainfall,
            "wind_speed_ms": session.wind_speed_ms,
            "drivers": [DriverSchema.from_orm(d) for d in drivers]
        }
        return cls(**data)
