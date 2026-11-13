"""Unit tests for the pure (DB-free) agent tool helpers."""

import gzip
import json
from pathlib import Path

from backend.agent import tools, types
from backend.config import settings


def _lap(lap_number, pit_in=None, pit_out=None, compound=None):
    return {
        "lap_number": lap_number,
        "pit_in_time_ms": pit_in,
        "pit_out_time_ms": pit_out,
        "compound": compound,
    }


def test_derive_pit_stops_handles_single_stop():
    laps = [
        _lap(1, compound="MEDIUM"),
        _lap(2, compound="MEDIUM"),
        _lap(3, pit_in=123456.0, compound="MEDIUM"),
        _lap(4, pit_out=234567.0, compound="HARD"),
        _lap(5, compound="HARD"),
    ]
    stops = tools._derive_pit_stops(laps)

    assert len(stops) == 1
    assert stops[0].stop_index == 1
    assert stops[0].pit_in_lap == 3
    assert stops[0].pit_out_lap == 4
    assert stops[0].compound_before == "MEDIUM"
    assert stops[0].compound_after == "HARD"


def test_derive_pit_stops_multiple_stops_are_numbered():
    laps = [
        _lap(1, compound="SOFT"),
        _lap(2, pit_in=1.0, compound="SOFT"),
        _lap(3, pit_out=2.0, compound="MEDIUM"),
        _lap(4, compound="MEDIUM"),
        _lap(5, pit_in=3.0, compound="MEDIUM"),
        _lap(6, pit_out=4.0, compound="HARD"),
    ]
    stops = tools._derive_pit_stops(laps)

    assert [s.stop_index for s in stops] == [1, 2]
    assert [s.pit_in_lap for s in stops] == [2, 5]
    assert [s.pit_out_lap for s in stops] == [3, 6]
    assert stops[1].compound_before == "MEDIUM"
    assert stops[1].compound_after == "HARD"


def test_derive_pit_stops_missing_pit_out_defaults_to_next_lap():
    laps = [
        _lap(10, compound="MEDIUM"),
        _lap(11, pit_in=1.0, compound="MEDIUM"),
    ]
    stops = tools._derive_pit_stops(laps)

    assert len(stops) == 1
    assert stops[0].pit_in_lap == 11
    assert stops[0].pit_out_lap == 12
    assert stops[0].compound_before == "MEDIUM"
    assert stops[0].compound_after is None


def _sample(lap_number, track_temp, rainfall):
    return types.WeatherEventSample(
        timestamp="2024-07-07T13:00:00Z",
        lap_number=lap_number,
        track_temp_c=track_temp,
        air_temp_c=15.0,
        humidity_pct=60.0,
        rainfall=rainfall,
        wind_speed_ms=3.5,
    )


def test_rain_stats_counts_rainy_laps_and_track_delta():
    samples = [
        _sample(1, 18.0, True),
        _sample(2, 20.0, False),
        _sample(3, 30.0, False),
        _sample(6, 22.0, True),
    ]
    stats = tools._rain_stats(samples)

    assert stats["rainfall_laps"] == 2
    assert stats["total_laps"] == 4
    assert stats["rain_share_pct"] == 50.0
    assert stats["track_temp_delta_c"] == 12.0  # 30 - 18


def test_rain_stats_empty_samples():
    stats = tools._rain_stats([])
    assert stats["rainfall_laps"] == 0
    assert stats["total_laps"] == 0
    assert stats["rain_share_pct"] == 0.0
    assert stats["track_temp_delta_c"] is None


def test_derive_pit_stops_no_pit_laps_returns_empty():
    laps = [_lap(1, compound="SOFT"), _lap(2, compound="SOFT")]
    assert tools._derive_pit_stops(laps) == []


# ── _mean ─────────────────────────────────────────────────────────────────────


def test_mean_averages_values():
    assert tools._mean([100.0, 200.0, 300.0]) == 200.0


def test_mean_empty_returns_zero():
    assert tools._mean([]) == 0.0


# ── _read_artifact_speed_samples ──────────────────────────────────────────────


def _write_json_gz_artifact(path: Path, samples: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as f:
        f.write(
            json.dumps(
                {
                    "session_key": 1,
                    "driver_number": 1,
                    "lap_number": 1,
                    "samples": samples,
                }
            ).encode("utf-8")
        )


def test_read_artifact_speed_samples_json_gz(monkeypatch, tmp_path):
    artifact = types.TelemetryArtifact(
        session_key=1,
        driver_number=1,
        lap_number=1,
        storage_key="telemetry/session_1/driver_1/lap_1.json.gz",
        storage_backend="local",
        format="json.gz",
        sample_count=3,
        size_bytes=100,
        checksum_sha256="x",
    )
    _write_json_gz_artifact(
        Path(tmp_path) / artifact.storage_key,
        [
            {"speed_kmh": 200.0},
            {"speed_kmh": 220.0},
            {"speed_kmh": None},
        ],
    )
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))

    speeds = tools._read_artifact_speed_samples(artifact)

    assert speeds == [200.0, 220.0]


def test_read_artifact_speed_samples_missing_file_raises(monkeypatch, tmp_path):
    artifact = types.TelemetryArtifact(
        session_key=1,
        driver_number=1,
        lap_number=999,
        storage_key="nonexistent.json.gz",
        storage_backend="local",
        format="json.gz",
        sample_count=0,
        size_bytes=0,
        checksum_sha256="x",
    )
    monkeypatch.setattr(settings, "telemetry_artifact_dir", str(tmp_path))

    try:
        tools._read_artifact_speed_samples(artifact)
    except types.DataError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected DataError for missing artifact file")


def test_read_artifact_speed_samples_unsupported_raises():
    artifact = types.TelemetryArtifact(
        session_key=1,
        driver_number=1,
        lap_number=1,
        storage_key="x.parquet",
        storage_backend="r2",
        format="json.gz",
        sample_count=0,
        size_bytes=0,
        checksum_sha256="x",
    )
    try:
        tools._read_artifact_speed_samples(artifact)
    except types.DataError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("expected DataError for unsupported artifact")


# ── _assess ───────────────────────────────────────────────────────────────────


def test_assess_all_passing_returns_passed():
    checks = [
        types.EvidenceCheck("a", True),
        types.EvidenceCheck("b", True),
    ]
    result = tools._assess(checks)
    assert result.passed is True
    assert result.refusal_reason is None
    assert len(result.checks) == 2


def test_assess_one_failure_returns_refusal():
    checks = [
        types.EvidenceCheck("a", True),
        types.EvidenceCheck("b", False, detail="missing telemetry"),
    ]
    result = tools._assess(checks)
    assert result.passed is False
    assert "b: missing telemetry" in result.refusal_reason


# ── compute_speed_window refusal paths (no DB needed) ─────────────────────────


def test_compute_speed_window_rejects_unsupported_metric():
    inp = types.ComputeSpeedWindowInput(
        session_key=1,
        driver_number=1,
        before_laps=(1, 2),
        metric=types.SpeedMetric.LAP_TIME_DERIVED,
    )
    try:
        tools.compute_speed_window(inp)
    except types.DataError as exc:
        assert "unsupported metric" in str(exc)
    else:
        raise AssertionError("expected DataError for unsupported metric")


def test_weighted_mean_basic():
    assert tools._weighted_mean([200.0, 200.0, 200.0], [100.0, 100.0, 100.0]) == 200.0


def test_weighted_mean_skews_toward_heavier():
    result = tools._weighted_mean([100.0, 200.0], [900.0, 100.0])
    assert round(result, 2) == 110.0


def test_weighted_mean_zero_weights_returns_zero():
    assert tools._weighted_mean([100.0, 200.0], [0.0, 0.0]) == 0.0


def test_compute_speed_window_rejects_empty_windows():
    inp = types.ComputeSpeedWindowInput(session_key=1, driver_number=1)
    try:
        tools.compute_speed_window(inp)
    except types.DataError as exc:
        assert "cannot both be empty" in str(exc)
    else:
        raise AssertionError("expected DataError for empty windows")


def _make_lap_event(
    lap_number,
    lap_time_ms=None,
    pit_in=False,
    pit_out=False,
    rainfall=False,
    track_status=None,
    compound="MEDIUM",
    stint=1,
):
    """Helper: build a raw LapEvent without typing every optional field."""
    return types.LapEvent(
        lap_number=lap_number,
        lap_time_ms=lap_time_ms,
        delta_to_median_ms=None,
        sector1_ms=None,
        sector2_ms=None,
        sector3_ms=None,
        compound=compound,
        stint=stint,
        is_pit_in=pit_in,
        is_pit_out=pit_out,
        is_anomaly=False,
        rainfall=rainfall,
        track_status=track_status,
    )


def test_detect_lap_anomalies_flags_slow_laps():
    """A lap 5s off the median is flagged; a 1s lap is fine."""
    events = [
        _make_lap_event(1, lap_time_ms=90000),
        _make_lap_event(2, lap_time_ms=95000),
        _make_lap_event(3, lap_time_ms=91000),
    ]
    flagged = tools._detect_lap_anomalies(events, median_ms=90000)
    assert [e.is_anomaly for e in flagged] == [False, True, False]


def test_detect_lap_anomalies_classifies_pit_stop():
    events = [_make_lap_event(10, lap_time_ms=115000, pit_in=True)]
    flagged = tools._detect_lap_anomalies(events, median_ms=90000)

    assert flagged[0].is_anomaly is True
    assert flagged[0].anomaly_reason == "pit_stop"


def test_detect_lap_anomalies_classifies_yellow_flag():
    """track_status='4' (VSC) explains an off-pace lap."""
    events = [_make_lap_event(20, lap_time_ms=100000, track_status="4")]
    flagged = tools._detect_lap_anomalies(events, median_ms=90000)

    assert flagged[0].anomaly_reason == "yellow_flag_vsc"


def test_detect_lap_anomalies_classifies_rain_onset():
    """First wet lap after dry laps is rain_onset."""
    events = [
        _make_lap_event(1, lap_time_ms=90000, rainfall=False),
        _make_lap_event(2, lap_time_ms=95000, rainfall=True),
    ]
    flagged = tools._detect_lap_anomalies(events, median_ms=90000)

    assert flagged[1].anomaly_reason == "rain_onset"


def test_detect_lap_anomalies_unknown_is_last_resort():
    """Slow lap with no pit/rain/flag gets the catch-all reason."""
    events = [_make_lap_event(5, lap_time_ms=95000)]
    flagged = tools._detect_lap_anomalies(events, median_ms=90000)

    assert flagged[0].is_anomaly is True
    assert flagged[0].anomaly_reason == "unknown_slowlap"


# stint degredation


def test_compute_stint_degradation_positive_slope():
    """+500ms/lap on a perfect line = degradation, no cliff."""
    laps = [
        {
            "lap_number": 5,
            "lap_time_ms": 90000,
            "compound": "MEDIUM",
            "stint": 1,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 6,
            "lap_time_ms": 90500,
            "compound": "MEDIUM",
            "stint": 1,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 7,
            "lap_time_ms": 91000,
            "compound": "MEDIUM",
            "stint": 1,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 8,
            "lap_time_ms": 91500,
            "compound": "MEDIUM",
            "stint": 1,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
    ]
    stints = tools._compute_stint_degradation(laps)

    assert len(stints) == 1
    assert stints[0].degradation_slope_ms_per_lap == 500.0
    assert stints[0].cliff_detected is False


def test_compute_stint_degradation_detects_cliff():
    """A lap 5.7s off the clean trend is a cliff at lap 14."""
    laps = [
        {
            "lap_number": 10,
            "lap_time_ms": 90000,
            "compound": "SOFT",
            "stint": 2,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 11,
            "lap_time_ms": 90100,
            "compound": "SOFT",
            "stint": 2,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 12,
            "lap_time_ms": 90200,
            "compound": "SOFT",
            "stint": 2,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 13,
            "lap_time_ms": 90300,
            "compound": "SOFT",
            "stint": 2,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 14,
            "lap_time_ms": 96000,
            "compound": "SOFT",
            "stint": 2,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
    ]
    stints = tools._compute_stint_degradation(laps)

    assert len(stints) == 1
    assert stints[0].cliff_detected is True
    assert stints[0].cliff_lap == 14


def test_compute_stint_degradation_skips_pit_laps():
    """Pit in/out laps must not corrupt the regression."""
    laps = [
        {
            "lap_number": 20,
            "lap_time_ms": 90000,
            "compound": "HARD",
            "stint": 3,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 21,
            "lap_time_ms": 110000,
            "compound": "HARD",
            "stint": 3,
            "pit_in_time_ms": 1.0,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 22,
            "lap_time_ms": 95000,
            "compound": "HARD",
            "stint": 3,
            "pit_in_time_ms": None,
            "pit_out_time_ms": 2.0,
        },
        {
            "lap_number": 23,
            "lap_time_ms": 90500,
            "compound": "HARD",
            "stint": 3,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
    ]
    stints = tools._compute_stint_degradation(laps)

    assert len(stints) == 1
    assert stints[0].total_laps == 2


def test_compute_stint_degradation_multiple_stints():
    """Different compound/stints produce separate summaries."""
    laps = [
        {
            "lap_number": 1,
            "lap_time_ms": 90000,
            "compound": "SOFT",
            "stint": 1,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 2,
            "lap_time_ms": 90500,
            "compound": "SOFT",
            "stint": 1,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 10,
            "lap_time_ms": 91000,
            "compound": "HARD",
            "stint": 2,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
        {
            "lap_number": 11,
            "lap_time_ms": 91200,
            "compound": "HARD",
            "stint": 2,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        },
    ]
    stints = tools._compute_stint_degradation(laps)

    assert len(stints) == 2
    assert stints[0].stint_index == 1
    assert stints[0].compound == "SOFT"
    assert stints[1].stint_index == 2
    assert stints[1].compound == "HARD"


def test_compute_stint_degradation_carries_lap_points():
    """Every clean lap becomes a (lap_number, tyre_age, lap_time_ms) scatter point."""
    laps = [
        {
            "lap_number": lap_no,
            "lap_time_ms": 90000 + (lap_no - 20) * 200,
            "compound": "HARD",
            "stint": 2,
            "pit_in_time_ms": None,
            "pit_out_time_ms": None,
        }
        for lap_no in range(20, 24)
    ]
    # a pit lap must be excluded from the series
    laps.append(
        {
            "lap_number": 24,
            "lap_time_ms": 120000,
            "compound": "HARD",
            "stint": 2,
            "pit_in_time_ms": 1.0,
            "pit_out_time_ms": None,
        }
    )

    stints = tools._compute_stint_degradation(laps)

    assert len(stints) == 1
    points = stints[0].laps
    assert [p.lap_number for p in points] == [20, 21, 22, 23]
    assert [p.tyre_age for p in points] == [1, 2, 3, 4]
    assert points[0].lap_time_ms == 90000
    assert points[-1].lap_time_ms == 90600


# telemetry resampling


def test_resample_telemetry_reduces_points():
    """1000 samples must shrink to <= max_points (max_points=100 here)."""
    samples = [
        {
            "distance_m": i * 1.0,
            "speed_kmh": 200.0,
            "throttle": 1.0,
            "brake": False,
            "gear": 7,
            "drs": 1,
        }
        for i in range(1000)
    ]
    result = tools._resample_telemetry(samples, max_points=100)

    assert len(result) <= 100
    assert isinstance(result[0], types.TelemetrySamplePoint)


def test_resample_telemetry_preserves_first_and_last():
    """First and last distance must survive the downsample."""
    samples = [
        {
            "distance_m": 0.0,
            "speed_kmh": 100.0,
            "throttle": 0.5,
            "brake": False,
            "gear": 1,
            "drs": 0,
        },
        {
            "distance_m": 100.0,
            "speed_kmh": 200.0,
            "throttle": 1.0,
            "brake": False,
            "gear": 8,
            "drs": 1,
        },
    ]
    result = tools._resample_telemetry(samples, max_points=600)

    assert len(result) == 2
    assert result[0].distance_m == 0.0
    assert result[-1].distance_m == 100.0


def test_resample_telemetry_single_point_when_max_points_one():
    """max_points=1 must not divide by zero — return one point."""
    samples = [
        {"distance_m": 0.0, "speed_kmh": 100.0},
        {"distance_m": 100.0, "speed_kmh": 200.0},
    ]
    result = tools._resample_telemetry(samples, max_points=1)

    assert len(result) == 1


def test_to_sample_point_scales_throttle():
    """fastf1 throttle 0.8 must become 80.0%."""
    raw = {
        "distance_m": 100.0,
        "speed_kmh": 250.0,
        "throttle": 0.8,
        "brake": False,
        "gear": 8,
        "drs": 1,
    }
    pt = tools._to_sample_point(raw)

    assert pt.throttle_pct == 80.0
    assert pt.speed_kmh == 250.0
    assert pt.gear == 8


def test_compute_trace_stats_counts_braking_zones():
    """Three separate brake presses -> heavy_braking_zones_count == 3."""
    samples = [
        types.TelemetrySamplePoint(0.0, 300.0, 100.0, False, 8, 1, None, None),
        types.TelemetrySamplePoint(100.0, 300.0, 100.0, False, 8, 1, None, None),
        types.TelemetrySamplePoint(200.0, 100.0, 0.0, True, 3, 0, None, None),
        types.TelemetrySamplePoint(300.0, 300.0, 100.0, False, 8, 1, None, None),
        types.TelemetrySamplePoint(400.0, 100.0, 0.0, True, 3, 0, None, None),
        types.TelemetrySamplePoint(500.0, 300.0, 100.0, False, 8, 1, None, None),
        types.TelemetrySamplePoint(600.0, 100.0, 0.0, True, 3, 0, None, None),
    ]
    throttle_pct, braking_zones = tools._compute_trace_stats(samples)

    assert braking_zones == 3
    assert throttle_pct > 0
