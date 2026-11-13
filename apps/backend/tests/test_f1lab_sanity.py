from backend.f1lab import sanity


def _codes(issues):
    return {i.code for i in issues}


def _lap(n=60, speed=250.0, **extra):
    return [{"distance_m": i * 80.0, "speed_kmh": speed, **extra} for i in range(n)]


def test_short_lap_time_is_an_error():
    assert _codes(sanity.check_lap_time(45_000)) == {"lap_time_too_short"}
    assert sanity.check_lap_time(95_000) == []


def test_degradation_rules():
    assert _codes(sanity.check_degradation(-0.126, fuel_corrected=False)) == {
        "deg_negative_uncorrected"
    }
    assert _codes(sanity.check_degradation(-0.2, fuel_corrected=True)) == {
        "deg_negative_corrected"
    }
    assert _codes(sanity.check_degradation(1.5, fuel_corrected=True)) == {
        "deg_too_high"
    }
    assert sanity.check_degradation(0.08, fuel_corrected=True) == []


def test_pit_loss_range_only_applies_to_green():
    assert _codes(sanity.check_pit_loss(41.5, "green")) == {"pit_loss_range"}
    assert sanity.check_pit_loss(24.0, "green") == []
    assert sanity.check_pit_loss(5.0, "vsc") == []
    assert sanity.check_pit_loss(None, "green") == []


def test_missing_throttle_channel_is_flagged_not_zero_filled():
    assert "throttle_missing" in _codes(sanity.check_telemetry(_lap()))


def test_all_zero_throttle_at_speed_is_an_error():
    assert "throttle_all_zero" in _codes(sanity.check_telemetry(_lap(throttle=0.0)))


def test_good_throttle_has_no_issue():
    samples = [
        {
            "distance_m": i * 80.0,
            "speed_kmh": 250.0,
            "throttle": 100.0 if i % 2 else 40.0,
        }
        for i in range(60)
    ]
    assert sanity.check_telemetry(samples) == []


def test_speed_and_distance_checks():
    bad = _lap(throttle=50.0)
    bad[3]["speed_kmh"] = 420.0
    bad[10]["distance_m"] = 0.0
    assert {"speed_range", "distance_not_monotonic"} <= _codes(
        sanity.check_telemetry(bad)
    )


def test_empty_telemetry_is_an_error():
    assert _codes(sanity.check_telemetry([])) == {"no_samples"}
