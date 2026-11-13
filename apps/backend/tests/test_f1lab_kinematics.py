import math

import pytest

from backend.f1lab.kinematics import (
    G,
    lateral_g,
    lateral_peak,
    longitudinal_g,
    moving_average,
    xy_scale_m_per_unit,
)


def _circle(radius_m=50.0, speed_kmh=180.0, spacing_m=2.0, arc=math.pi, scale=0.1):
    """Constant-speed arc. X/Y are stored in 1/10 m like FastF1 positions."""
    n = int(radius_m * arc / spacing_m)
    samples = []
    for i in range(n):
        theta = i * spacing_m / radius_m
        samples.append(
            {
                "distance_m": i * spacing_m,
                "speed_kmh": speed_kmh,
                "x_pos": radius_m * math.cos(theta) / scale,
                "y_pos": radius_m * math.sin(theta) / scale,
            }
        )
    return samples


def test_xy_scale_recovers_tenth_of_a_metre():
    assert xy_scale_m_per_unit(_circle()) == 0.1


def test_xy_scale_is_none_without_movement():
    still = [{"distance_m": 0.0, "x_pos": 1.0, "y_pos": 1.0, "speed_kmh": 0}] * 3
    assert xy_scale_m_per_unit(still) is None


def test_circle_lateral_g_matches_v_squared_over_r():
    v = 180 / 3.6
    expected = v * v / 50.0 / G  # ~5.1 g
    values = [g for g in lateral_g(_circle()) if g is not None]
    mid = values[len(values) // 2]
    assert mid == pytest.approx(expected, rel=0.03)


def test_straight_line_has_no_lateral_g():
    straight = [
        {"distance_m": i * 5.0, "speed_kmh": 300.0, "x_pos": i * 50.0, "y_pos": 0.0}
        for i in range(40)
    ]
    assert max(g for g in lateral_g(straight) if g is not None) == pytest.approx(
        0.0, abs=1e-6
    )


def test_edges_are_none():
    values = lateral_g(_circle(), step=3)
    assert values[:3] == [None] * 3 and values[-3:] == [None] * 3


def test_lateral_peak_reports_a_range_around_the_truth():
    peak = lateral_peak(_circle())
    expected = (180 / 3.6) ** 2 / 50.0 / G
    assert peak.low_g <= peak.value_g <= peak.high_g
    assert peak.value_g == pytest.approx(expected, rel=0.05)


def test_constant_acceleration_gives_longitudinal_g():
    a = 10.0  # m/s^2
    v0 = 40.0
    samples = []
    for i in range(60):
        s = i * 5.0
        v = math.sqrt(v0 * v0 + 2 * a * s)
        samples.append({"distance_m": s, "speed_kmh": v * 3.6})
    values = [g for g in longitudinal_g(samples) if g is not None]
    assert values[len(values) // 2] == pytest.approx(a / G, rel=0.03)


def test_braking_is_negative():
    samples = [{"distance_m": i * 5.0, "speed_kmh": 300 - i * 4.0} for i in range(40)]
    assert min(g for g in longitudinal_g(samples) if g is not None) < 0


def test_moving_average_shrinks_window_at_edges():
    assert moving_average([0.0, 3.0, 6.0], 3) == [1.5, 3.0, 4.5]
