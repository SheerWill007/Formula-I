"""
Session ORM model.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class Session(Base):
    __tablename__ = "sessions"

    session_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    gp_name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    session_type: Mapped[str] = mapped_column(String, nullable=False)  # Q, R, FP1, etc.
    session_name: Mapped[str] = mapped_column(String, nullable=False)
    date_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Weather data
    track_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    air_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rainfall: Mapped[Optional[bool]] = mapped_column(nullable=True)
    wind_speed_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    drivers: Mapped[List["Driver"]] = relationship(
        "Driver", back_populates="session", cascade="all, delete-orphan"
    )
    lap_times: Mapped[List["LapTime"]] = relationship(
        "LapTime", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Session {self.year} {self.gp_name} {self.session_type}>"
