import pytest

from backend.f1lab.pace import clean_laps, fit_degradation, fuel_correct

TOTAL = 57


def _stint(deg=0.08, fuel=0.05, first=2, n=20):
    # true model: base + deg*tyre_age + fuel*laps_of_fuel_remaining
    return [
        {
            "lap_number": lap,
            "lap_time_ms": round(
                (95.0 + deg * (lap - first) + fuel * (TOTAL - lap)) * 1000
            ),
            "stint": 1,
        }
        for lap in range(first, first + n)
    ]


def test_raw_slope_hides_degradation_and_fuel_correction_recovers_it():
    laps = _stint()
    raw = fit_degradation(laps)
    fixed = fit_degradation(fuel_correct(laps, TOTAL))
    assert raw.slope_s_per_lap == pytest.approx(0.03, abs=1e-3)  # deg 0.08 - fuel 0.05
    assert fixed.slope_s_per_lap == pytest.approx(0.08, abs=1e-3)
    assert fixed.r2 > 0.999


def test_fuel_correct_does_not_mutate_input():
    laps = _stint(n=3)
    before = [dict(lap) for lap in laps]
    fuel_correct(laps, TOTAL)
    assert laps == before


def test_clean_laps_drops_start_pit_sc_deleted_and_slow_outlier():
    laps = _stint(n=6)
    laps.append({"lap_number": 1, "lap_time_ms": 103000, "stint": 1})
    laps.append(
        {"lap_number": 9, "lap_time_ms": 96000, "stint": 1, "pit_in_time_ms": 1}
    )
    laps.append(
        {"lap_number": 10, "lap_time_ms": 96000, "stint": 1, "track_status": "14"}
    )
    laps.append({"lap_number": 11, "lap_time_ms": 96000, "stint": 1, "deleted": True})
    laps.append({"lap_number": 12, "lap_time_ms": 120000, "stint": 1})
    kept = clean_laps(laps)
    assert [lap["lap_number"] for lap in kept] == [2, 3, 4, 5, 6, 7]


def test_too_few_laps_returns_none():
    assert fit_degradation(_stint(n=4)) is None


def test_nan_is_treated_like_missing_so_pandas_laps_work():
    nan = float("nan")
    laps = [
        {
            "lap_number": n,
            "lap_time_ms": 95000.0 + n,
            "stint": 1,
            "pit_in_time_ms": nan,
            "pit_out_time_ms": nan,
            "track_status": None,
        }
        for n in range(2, 12)
    ]
    laps.append({"lap_number": 12, "lap_time_ms": nan, "stint": 1})
    kept = clean_laps(laps)
    assert [lap["lap_number"] for lap in kept] == list(range(2, 12))
