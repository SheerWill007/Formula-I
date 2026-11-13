import pytest
from sqlalchemy import text

from backend.f1lab import data

SK = 99971


@pytest.fixture()
def seeded(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sessions (session_key, year, gp_name, session_type, session_name) "
                "VALUES (:sk, 2026, 'F1lab Test Grand Prix', 'R', 'Race')"
            ),
            {"sk": SK},
        )
        for number, abbr, name in (
            (44, "HAM", "Lewis Hamilton"),
            (63, "RUS", "George Russell"),
        ):
            conn.execute(
                text(
                    "INSERT INTO drivers (driver_number, session_key, full_name, abbreviation) "
                    "VALUES (:n, :sk, :name, :abbr)"
                ),
                {"n": number, "sk": SK, "name": name, "abbr": abbr},
            )
        for lap in (1, 2, 3):
            conn.execute(
                text(
                    "INSERT INTO lap_times (session_key, driver_number, lap_number, lap_time_ms, "
                    "deleted, is_personal_best, recorded_at) "
                    "VALUES (:sk, 44, :lap, 95000, :deleted, false, NOW())"
                ),
                {"sk": SK, "lap": lap, "deleted": lap == 3},
            )
        conn.execute(
            text(
                "INSERT INTO lap_times (session_key, driver_number, lap_number, lap_time_ms, "
                "deleted, is_personal_best, recorded_at) "
                "VALUES (:sk, 63, 1, 96000, false, false, NOW())"
            ),
            {"sk": SK},
        )
    yield
    with db_engine.begin() as conn:
        for table in ("lap_times", "drivers", "sessions"):
            conn.execute(
                text(f"DELETE FROM {table} WHERE session_key = :sk"), {"sk": SK}
            )


def test_resolve_driver_by_abbreviation_and_name(db_engine, seeded):
    with db_engine.connect() as conn:
        assert data.resolve_driver_number(conn, SK, "ham") == 44
        assert data.resolve_driver_number(conn, SK, "Russell") == 63
        assert data.resolve_driver_number(conn, SK, "Senna") is None


def test_load_laps_skips_deleted_and_filters_driver(db_engine, seeded):
    with db_engine.connect() as conn:
        everyone = data.load_laps(conn, SK)
        ham = data.load_laps(conn, SK, driver_number=44)
    assert [(lap["driver_number"], lap["lap_number"]) for lap in everyone] == [
        (44, 1),
        (44, 2),
        (63, 1),
    ]
    assert [lap["lap_number"] for lap in ham] == [1, 2]
    assert data.race_length(everyone) == 2
    assert data.race_length([]) == 0


def test_include_deleted_keeps_laps_needed_for_gaps(db_engine, seeded):
    with db_engine.connect() as conn:
        laps = data.load_laps(conn, SK, driver_number=44, include_deleted=True)
    assert [lap["lap_number"] for lap in laps] == [1, 2, 3]
    assert laps[2]["deleted"] is True
