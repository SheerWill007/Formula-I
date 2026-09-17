"""
Driver ORM model.
"""
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base

if TYPE_CHECKING:
    from backend.models.session import Session
    from backend.models.lap_time import LapTime


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[int] = mapped_column(
        Integer, ForeignKey("sessions.session_key", ondelete="CASCADE"), nullable=False, index=True
    )
    driver_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    abbreviation: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    team_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    team_colour: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="drivers")
    lap_times: Mapped[List["LapTime"]] = relationship(
        "LapTime", back_populates="driver", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Driver #{self.driver_number} {self.full_name}>"
