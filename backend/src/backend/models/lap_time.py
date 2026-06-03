"""
LapTime ORM model.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Integer, String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.session import Session
    from backend.models.driver import Driver


class LapTime(Base):
    __tablename__ = "lap_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[int] = mapped_column(
        Integer, ForeignKey("sessions.session_key", ondelete="CASCADE"), nullable=False
    )
    driver_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lap_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lap_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Timing sectors
    # Database uses s1_ms, s2_ms, s3_ms
    sector_1_ms: Mapped[Optional[float]] = mapped_column("s1_ms", Float, nullable=True)
    sector_2_ms: Mapped[Optional[float]] = mapped_column("s2_ms", Float, nullable=True)
    sector_3_ms: Mapped[Optional[float]] = mapped_column("s3_ms", Float, nullable=True)
    
    # Speed traps (FIA timing points)
    speed_i1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed_i2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed_fl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed_st: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Race data
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    compound: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tyre_life: Mapped[Optional[int]] = mapped_column("tyre_life_laps", Integer, nullable=True)
    stint: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Pit stop data
    pit_in_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pit_out_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    track_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Flags
    is_personal_best: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fresh_tyre: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Qualifying segment
    quali_segment: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)  # Q1, Q2, Q3
    
    # Telemetry stats (aggregated from full telemetry data)
    avg_speed_kph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_speed_kph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_throttle_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_brake_pressure: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_rpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_rpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    recorded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="lap_times")
    driver: Mapped["Driver"] = relationship("Driver", back_populates="lap_times")

    __table_args__ = (
        Index("idx_lap_times_session_driver", "session_key", "driver_number"),
        Index("idx_lap_times_session_lap", "session_key", "lap_number"),
    )

    def __repr__(self) -> str:
        return f"<LapTime session={self.session_key} driver={self.driver_number} lap={self.lap_number}>"
