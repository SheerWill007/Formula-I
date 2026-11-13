"""Load lap data for f1lab. The only f1lab module that touches the database.

Takes a SQLAlchemy connection so tests and scripts can point it at any DB.
"""

from __future__ import annotations

from sqlalchemy import text

_LAP_COLUMNS = """
    driver_number, lap_number, lap_time_ms, s1_ms, s2_ms, s3_ms, compound,
    stint, tyre_life_laps, pit_in_time_ms, pit_out_time_ms, track_status,
    position, deleted
"""


def resolve_driver_number(conn, session_key: int, name: str) -> int | None:
    """Driver number from an abbreviation ('HAM') or part of a full name."""
    row = conn.execute(
        text(
            """
            SELECT driver_number FROM drivers
            WHERE session_key = :sk
              AND (UPPER(abbreviation) = UPPER(:n) OR full_name ILIKE :like)
            ORDER BY (UPPER(abbreviation) = UPPER(:n)) DESC
            LIMIT 1
            """
        ),
        {"sk": session_key, "n": name, "like": f"%{name}%"},
    ).first()
    return int(row[0]) if row else None


def load_laps(
    conn,
    session_key: int,
    driver_number: int | None = None,
    *,
    include_deleted: bool = False,
) -> list[dict]:
    """Laps as dicts, ordered by driver then lap.

    Deleted laps are left out by default. A lap deleted for track limits was still
    driven, so anything summing lap times (gaps) needs include_deleted=True.
    """
    sql = f"""
        SELECT {_LAP_COLUMNS}
        FROM lap_times
        WHERE session_key = :sk
    """
    if not include_deleted:
        sql += " AND deleted = FALSE"
    binds: dict = {"sk": session_key}
    if driver_number is not None:
        sql += " AND driver_number = :dn"
        binds["dn"] = driver_number
    sql += " ORDER BY driver_number, lap_number"
    return [dict(r) for r in conn.execute(text(sql), binds).mappings().all()]


def race_length(laps: list[dict]) -> int:
    """Number of laps in the race: the highest lap number seen."""
    return max((lap["lap_number"] for lap in laps), default=0)
