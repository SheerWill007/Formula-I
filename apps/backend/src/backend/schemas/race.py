"""
Race result Pydantic schemas.
"""
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RaceResultResponse(BaseModel):
    """Race result response schema."""
    driver_number: int
    full_name: str
    abbreviation: Optional[str] = None
    team_name: Optional[str] = None
    team_colour: Optional[str] = None
    total_laps: int
    finish_pos: Optional[int] = None
    compound: Optional[str] = None
    best_lap_ms: Optional[float] = None
    total_ms: Optional[float] = None
    gap_ms: Optional[float] = None
    laps_down: int = 0

    model_config = ConfigDict(from_attributes=True)
