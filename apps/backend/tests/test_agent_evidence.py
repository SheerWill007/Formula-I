"""Integration tests for agent tools against the real (test) database.

These exercise the full evidence chain:
  session + driver rows -> lap_times with pit flags
  -> telemetry_artifacts json.gz files -> compute_speed_window -> verify_evidence
"""

import gzip
import json
from pathlib import Path

from sqlalchemy import text

from backend.agent import tools, types
from backend.config import settings

SESSION_KEY = 99995


def _insert_session_and_driver(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sessions (
                    session_key, year, gp_name, country, session_type, session_name
                ) VALUES (
                    :sk, 2024, 'Silverstone GP', 'UK', 'R', 'Race'
                )
                """
            ),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text(
                """
                INSERT INTO drivers (
                    driver_number, session_key, full_name, abbreviation, team_name, team_colour
                ) VALUES (
                    1, :sk, 'Max Verstappen', 'VER', 'Red Bull Racing', '3671C6'
                )
                """
            ),
            {"sk": SESSION_KEY},
        )


def _insert_laps(db_engine):
    """Laps 1-4 clean, lap 5 pit_in, lap 6 pit_out. Stops detected on lap 5/6."""
    with db_engine.begin() as conn:
        for lap, compound, pit_in, pit_out in [
            (1, "SOFT", None, None),
            (2, "SOFT", None, None),
            (3, "SOFT", None, None),
            (4, "SOFT", None, None),
            (5, "SOFT", 123456.0, None),
            (6, "HARD", None, 234567.0),
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO lap_times (
                        session_key, driver_number, lap_number, lap_time_ms,
                        compound, pit_in_time_ms, pit_out_time_ms,
                        is_personal_best, deleted, recorded_at
                    ) VALUES (
                        :sk, 1, :lap, 100000, :compound, :pit_in, :pit_out,
                        false, false, NOW()
                    )
                    """
                ),
                {
                    "sk": SESSION_KEY,
                    "lap": lap,
                    "compound": compound,
                    "pit_in": pit_in,
                    "pit_out": pit_out,
                },
            )


def _write_gz_artifact(tmp_path, lap_number, speeds):
    storage_key = f"telemetry/session_{SESSION_KEY}/driver_1/lap_{lap_number}.json.gz"
    path = Path(tmp_path) / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = [{"speed_kmh": s} for s in speeds]
    with gzip.open(path, "wb") as f:
        f.write(
            json.dumps(
                {
                    "session_key": SESSION_KEY,
                    "driver_number": 1,
                    "lap_number": lap_number,
                    "samples": samples,
                }
            ).encode("utf-8")
        )
    with path.open("rb") as f:
        size = len(f.read())
    return storage_key, size


def _insert_artifacts(db_engine, tmp_path):
    """Artifacts for laps 3,4 (before) and 7,8 (after) — note: lap 7/8 are NOT in lap_times."""
    entries = []
    for lap_number, speeds in [
        (3, [200.0, 210.0]),
        (4, [220.0, 230.0]),
        (7, [240.0, 250.0]),
        (8, [260.0, 270.0]),
    ]:
        storage_key, size = _write_gz_artifact(tmp_path, lap_number, speeds)
        entries.append((lap_number, storage_key, size, len(speeds)))
    with db_engine.begin() as conn:
        for lap_number, storage_key, size, count in entries:
            conn.execute(
                text(
                    """
                    INSERT INTO telemetry_artifacts (
                        session_key, driver_number, lap_number,
                        storage_key, storage_backend, format,
                        sample_count, size_bytes, checksum_sha256
                    ) VALUES (
                        :sk, 1, :lap, :key, 'local', 'json.gz', :count, :size, 'test'
                    )
                    """
                ),
                {
                    "sk": SESSION_KEY,
                    "lap": lap_number,
                    "key": storage_key,
                    "count": count,
                    "size": size,
                },
            )


def _cleanup(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM telemetry_artifacts WHERE session_key = :sk"),
            {"sk": SESSION_KEY},
        )
        conn.execute(
            text("DELETE FROM lap_times WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM drivers WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM sessions WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )


def test_full_evidence_chain(app, db_engine, monkeypatch, tmp_path):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))

    try:
        pits = tools.find_pit_stops(
            types.FindPitStopsInput(session_key=SESSION_KEY, driver_number=1)
        )
        assert len(pits.pit_stops) == 1
        stop = pits.pit_stops[0]
        assert stop.pit_in_lap == 5
        assert stop.pit_out_lap == 6
        assert stop.compound_before == "SOFT"
        assert stop.compound_after == "HARD"

        window = tools.compute_speed_window(
            types.ComputeSpeedWindowInput(
                session_key=SESSION_KEY,
                driver_number=1,
                before_laps=(3, 4),
                after_laps=(7, 8),
            )
        )
        # before: (200+210+220+230)/4 = 215.0 ; after: (240+250+260+270)/4 = 255.0
        assert window.before_avg_speed_kmh == 215.0
        assert window.after_avg_speed_kmh == 255.0
        assert window.delta_kmh == 40.0
        assert window.sample_count_before == 4
        assert window.sample_count_after == 4

        verify = tools.verify_evidence(
            types.VerifyEvidenceInput(
                session_key=SESSION_KEY,
                driver_number=1,
                required_laps=(3, 4, 7, 8),
            )
        )
        assert verify.passed is True
        assert verify.refusal_reason is None
    finally:
        _cleanup(db_engine)


def test_verify_evidence_refuses_missing_artifacts(
    app, db_engine, monkeypatch, tmp_path
):
    _insert_session_and_driver(db_engine)
    _insert_laps(db_engine)
    _insert_artifacts(db_engine, tmp_path)  # only laps 3,4,7,8
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))

    try:
        verify = tools.verify_evidence(
            types.VerifyEvidenceInput(
                session_key=SESSION_KEY,
                driver_number=1,
                required_laps=(3, 4, 7, 8, 9),  # lap 9 has no artifact
            )
        )
        assert verify.passed is False
        assert "missing laps [9]" in verify.refusal_reason
    finally:
        _cleanup(db_engine)


def test_compute_speed_window_refuses_missing_artifact_lap(
    app, db_engine, monkeypatch, tmp_path
):
    _insert_session_and_driver(db_engine)
    _insert_artifacts(
        db_engine, tmp_path
    )  # no lap 3/4 -> but 3,4 exist; use lap 9 in window
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))

    try:
        tools.compute_speed_window(
            types.ComputeSpeedWindowInput(
                session_key=SESSION_KEY,
                driver_number=1,
                before_laps=(3, 9),  # lap 9 artifact missing
                after_laps=(7, 8),
            )
        )
        raise AssertionError("expected DataError for missing artifact lap")
    except types.DataError as exc:
        assert "9" in str(exc)
    finally:
        _cleanup(db_engine)


# ── Team radio (Item 4) ──────────────────────────────────────────────────────


def _insert_team_radio(db_engine):
    with db_engine.begin() as conn:
        for lap, url, transcript in [
            (2, "https://cdn.f1.com/clip_02.mp3", "Box box box"),
            (5, "https://cdn.f1.com/clip_05.mp3", None),
            (6, "https://cdn.f1.com/clip_06.mp3", "Tyre degradation high"),
            (9, "https://cdn.f1.com/clip_09.mp3", "Race control says green"),
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO team_radio (
                        session_key, driver_number, lap_number, date, recording_url, transcript
                    ) VALUES (
                        :sk, 1, :lap, NOW() + :lap * INTERVAL '1 minute', :url, :transcript
                    )
                    """
                ),
                {"sk": SESSION_KEY, "lap": lap, "url": url, "transcript": transcript},
            )


def _cleanup_radio_weather(db_engine):
    with db_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM team_radio WHERE session_key = :sk"), {"sk": SESSION_KEY}
        )
        conn.execute(
            text("DELETE FROM weather_events WHERE session_key = :sk"),
            {"sk": SESSION_KEY},
        )


def test_fetch_radio_messages_window(app, db_engine):
    _insert_session_and_driver(db_engine)
    _insert_team_radio(db_engine)
    try:
        result = tools.fetch_radio_messages(
            types.RadioWindowInput(
                session_key=SESSION_KEY, driver_number=1, from_lap=5, to_lap=6
            )
        )
        assert result.clip_count == 2
        assert [m.transcript for m in result.messages] == [
            None,
            "Tyre degradation high",
        ]
        assert all(m.recording_url for m in result.messages)
    finally:
        _cleanup_radio_weather(db_engine)
        _cleanup(db_engine)


# ── Weather correlation (Item 5) ─────────────────────────────────────────────


def _insert_weather_events(db_engine):
    with db_engine.begin() as conn:
        rows = [
            (1, 18.0, True),
            (2, 20.0, False),
            (3, 26.0, False),
            (4, 30.0, False),
            (5, 28.0, False),
            (6, 22.0, True),
        ]
        for lap, track_temp, rain in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO weather_events (
                        session_key, timestamp, lap_number,
                        track_temp_c, air_temp_c, humidity_pct,
                        rainfall, wind_speed_ms
                    ) VALUES (
                        :sk, NOW() + :lap * INTERVAL '1 minute', :lap,
                        :tt, 15.0, 60.0, :rain, 3.5
                    )
                    """
                ),
                {"sk": SESSION_KEY, "lap": lap, "tt": track_temp, "rain": rain},
            )


def test_fetch_weather_window_rain_stats(app, db_engine):
    _insert_session_and_driver(db_engine)
    _insert_weather_events(db_engine)
    try:
        result = tools.fetch_weather_window(
            types.WeatherWindowInput(session_key=SESSION_KEY, from_lap=1, to_lap=6)
        )
        assert result.total_laps == 6
        assert result.rainfall_laps == 2  # laps 1 and 6
        assert result.rain_share_pct == 33.33
        assert result.track_temp_delta_c == 12.0  # 30 - 18
        assert len(result.samples) == 6
    finally:
        _cleanup_radio_weather(db_engine)
        _cleanup(db_engine)


def test_fetch_weather_window_empty_window(app, db_engine):
    _insert_session_and_driver(db_engine)
    _insert_weather_events(db_engine)
    try:
        result = tools.fetch_weather_window(
            types.WeatherWindowInput(session_key=SESSION_KEY, from_lap=99, to_lap=100)
        )
        assert result.samples == ()
        assert result.total_laps == 0
        assert result.rain_share_pct == 0.0
    finally:
        _cleanup_radio_weather(db_engine)
        _cleanup(db_engine)
