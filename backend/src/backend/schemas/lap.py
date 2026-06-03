"""
Lap time Pydantic schemas.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class LapTimeResponse(BaseModel):
    """Lap time response schema."""
    driver_number: int
    lap_number: int
    lap_time_ms: Optional[float] = None
    sector_1_ms: Optional[float] = None
    sector_2_ms: Optional[float] = None
    sector_3_ms: Optional[float] = None
    speed_i1: Optional[float] = None
    speed_i2: Optional[float] = None
    speed_fl: Optional[float] = None
    speed_st: Optional[float] = None
    position: Optional[int] = None
    compound: Optional[str] = None
    tyre_life: Optional[int] = None
    stint: Optional[int] = None
    is_personal_best: Optional[bool] = None
    deleted: bool = False
    fresh_tyre: Optional[bool] = None
    quali_segment: Optional[str] = None
    avg_speed_kph: Optional[float] = None
    max_speed_kph: Optional[float] = None
    recorded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm(cls, obj):
        """Create from ORM model."""
        return cls.model_validate(obj)


class FastestLapResponse(BaseModel):
    """Fastest lap response with driver info."""
    driver_number: int
    lap_number: int
    lap_time_ms: float
    sector_1_ms: Optional[float] = None
    sector_2_ms: Optional[float] = None
    sector_3_ms: Optional[float] = None
    compound: Optional[str] = None
    quali_segment: Optional[str] = None
    full_name: str
    abbreviation: Optional[str] = None
    team_name: Optional[str] = None
    team_colour: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
