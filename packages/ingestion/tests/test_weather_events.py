import pandas as pd

from ingestion.fastf1_client import extract_weather_events


class _FakeSession:
    def __init__(self, laps, weather_data, t0_date):
        self.laps = laps
        self.weather_data = weather_data
        self.t0_date = t0_date


def _make_weather(relative_times, rainfall_flags):
    # FastF1 3.8.1 weather_data: RangeIndex + t0-relative Time column.
    return pd.DataFrame(
        {
            "Time": [
                pd.Timedelta(t) if not isinstance(t, str) else pd.to_timedelta(t)
                for t in relative_times
            ],
            "AirTemp": [20.0, 21.0, 22.0],
            "TrackTemp": [30.0, 31.0, 32.0],
            "Humidity": [50.0, 51.0, 52.0],
            "Rainfall": rainfall_flags,
            "WindSpeed": [2.0, 3.0, 4.0],
        }
    )


def test_extract_weather_events_absolute_clock_with_telemetry():
    # With telemetry loaded, LapStartDate is absolute and derived from t0_date.
    t0 = pd.Timestamp("2024-07-07 13:04:57.029", tz="UTC")
    lap_starts = pd.to_datetime(
        ["2024-07-07 13:05:00", "2024-07-07 13:09:00", "2024-07-07 13:15:00"],
        utc=True,
    )
    laps = pd.DataFrame(
        {
            "DriverNumber": [63, 63, 63],
            "LapNumber": [1, 2, 3],
            "LapStartDate": lap_starts,
        }
    )
    # Sample 0 at +3s (pre-lap-1 / formation), sample 1 at +10min (lap 2),
    # sample 2 at +30min (after lap 3).
    weather = _make_weather(["00:03:00", "00:10:00", "00:30:00"], [False, True, False])
    session = _FakeSession(laps, weather, t0)

    rows = extract_weather_events(session, session_key=9554)

    assert len(rows) == 3
    assert [r["lap_number"] for r in rows] == [1, 2, 3]
    assert [r["timestamp"] for r in rows] == [
        str(t0 + pd.Timedelta("00:03:00")),
        str(t0 + pd.Timedelta("00:10:00")),
        str(t0 + pd.Timedelta("00:30:00")),
    ]
    assert [r["air_temp_c"] for r in rows] == [20.0, 21.0, 22.0]
    assert [r["track_temp_c"] for r in rows] == [30.0, 31.0, 32.0]
    assert [r["humidity_pct"] for r in rows] == [50.0, 51.0, 52.0]
    assert [r["wind_speed_ms"] for r in rows] == [2.0, 3.0, 4.0]
    assert [r["rainfall"] for r in rows] == [False, True, False]
    assert {r["session_key"] for r in rows} == {9554}


def test_extract_weather_events_relative_clock_without_telemetry():
    # FastF1 Laps without telemetry: only session-relative LapStartTime.
    lap_starts = pd.to_timedelta(["00:01:00", "00:05:00", "00:11:00"])
    laps = pd.DataFrame(
        {
            "DriverNumber": [63, 63, 63],
            "LapNumber": [1, 2, 3],
            "LapStartTime": lap_starts,
            "LapStartDate": [pd.NaT] * 3,
        }
    )
    weather = _make_weather(["00:03:00", "00:10:00", "00:30:00"], [False, True, False])
    session = _FakeSession(laps, weather, t0_date=None)

    rows = extract_weather_events(session, session_key=9554)

    assert len(rows) == 3
    assert [r["lap_number"] for r in rows] == [1, 2, 3]
    assert [r["timestamp"] for r in rows] == [
        "0 days 00:03:00",
        "0 days 00:10:00",
        "0 days 00:30:00",
    ]


def test_extract_weather_events_empty_weather():
    session = _FakeSession(pd.DataFrame(), pd.DataFrame(), t0_date=None)

    rows = extract_weather_events(session, session_key=9554)

    assert rows == []
