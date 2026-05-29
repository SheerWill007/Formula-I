"""Tests for qualifying segment analysis."""

from sqlalchemy import text


def test_quali_segments_uses_stored_quali_segment(client, db_engine):
    session_key = 99998

    with db_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO sessions (
                session_key, year, gp_name, country, session_type, session_name
            ) VALUES (
                :sk, 2024, 'Stored Segment Grand Prix', 'Testland', 'Q', 'Qualifying'
            )
        """), {"sk": session_key})

        conn.execute(text("""
            INSERT INTO drivers (
                driver_number, session_key, full_name, abbreviation, team_name, team_colour
            ) VALUES
                (44, :sk, 'Lewis Hamilton', 'HAM', 'Mercedes', '27F4D2'),
                (63, :sk, 'George Russell', 'RUS', 'Mercedes', '27F4D2')
        """), {"sk": session_key})

        conn.execute(text("""
            INSERT INTO lap_times (
                session_key, driver_number, lap_number, lap_time_ms,
                s1_ms, s2_ms, s3_ms, compound, is_personal_best,
                deleted, recorded_at, quali_segment
            ) VALUES
                (:sk, 44, 2, 88000, 27500, 35000, 25500, 'SOFT', true, false, NOW(), 1),
                (:sk, 63, 2, 87000, 27000, 34500, 25500, 'SOFT', true, false, NOW(), 1),
                (:sk, 44, 6, 86000, 26800, 34000, 25200, 'SOFT', true, false, NOW(), 2),
                (:sk, 63, 5, 85800, 26700, 33900, 25200, 'SOFT', true, false, NOW(), 2),
                (:sk, 44, 9, 85000, 26500, 33500, 25000, 'SOFT', true, false, NOW(), 3),
                (:sk, 63, 8, 84800, 26400, 33400, 25000, 'SOFT', true, false, NOW(), 3)
        """), {"sk": session_key})

    try:
        data = client.get(f"/api/v1/sessions/{session_key}/analysis/quali-segments").get_json()

        assert data["boundaries"]["Q2_start_lap"] == 5
        assert data["boundaries"]["Q3_start_lap"] == 8
        assert {row["driver_number"] for row in data["segments"]["Q1"]} == {44, 63}
        assert {row["driver_number"] for row in data["segments"]["Q2"]} == {44, 63}
        assert {row["driver_number"] for row in data["segments"]["Q3"]} == {44, 63}
        assert {row["driver_number"]: row["lap_number"] for row in data["segments"]["Q2"]} == {44: 6, 63: 5}
        assert {row["driver_number"]: row["lap_number"] for row in data["segments"]["Q3"]} == {44: 9, 63: 8}
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM lap_times WHERE session_key = :sk"), {"sk": session_key})
            conn.execute(text("DELETE FROM drivers WHERE session_key = :sk"), {"sk": session_key})
            conn.execute(text("DELETE FROM sessions WHERE session_key = :sk"), {"sk": session_key})
