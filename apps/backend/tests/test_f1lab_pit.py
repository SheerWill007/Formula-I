import pytest

from backend.f1lab.pit import PitLoss, lap_condition, pit_losses, summarize_green

TOTAL = 57


def _race(stop_in=15, extra_s=12.0, status=None, n_laps=30):
    """Flat 95 s pace + fuel effect; in/out laps each cost extra_s."""
    laps = []
    for lap in range(2, n_laps + 1):
        t = 95.0 + 0.05 * (TOTAL - lap)
        row = {"lap_number": lap, "stint": 1 if lap <= stop_in else 2}
        if lap in (stop_in, stop_in + 1):
            t += extra_s
            row["track_status"] = status
        if lap == stop_in:
            row["pit_in_time_ms"] = 1
        if lap == stop_in + 1:
            row["pit_out_time_ms"] = 1
        row["lap_time_ms"] = round(t * 1000)
        laps.append(row)
    return laps


def test_green_stop_recovers_the_known_loss():
    [stop] = pit_losses(_race(), TOTAL)
    assert (stop.lap_in, stop.lap_out, stop.condition) == (15, 16, "green")
    assert stop.loss_s == pytest.approx(24.0, abs=0.01)  # 2 x 12 s
    assert stop.ref_laps == 6


def test_safety_car_stop_is_not_given_a_number():
    [stop] = pit_losses(_race(status="4"), TOTAL)
    assert stop.condition == "sc"
    assert stop.loss_s is None


def test_too_few_reference_laps_gives_none():
    [stop] = pit_losses(
        _race(stop_in=3, n_laps=4), TOTAL
    )  # lap 2 before, nothing after
    assert stop.loss_s is None


def test_lap_condition_worst_code_wins():
    assert lap_condition("1") == "green"
    assert lap_condition("671") == "vsc"
    assert lap_condition("14") == "sc"
    assert lap_condition("5") == "red"
    assert lap_condition(None) == "green"


def test_summary_ignores_unmeasured_and_non_green():
    stops = [
        PitLoss(10, 11, "green", 22.0, 6),
        PitLoss(30, 31, "green", 26.0, 6),
        PitLoss(40, 41, "sc", None, 6),
        PitLoss(50, 51, "green", None, 1),
    ]
    assert summarize_green(stops) == {
        "n": 2,
        "median_s": 24.0,
        "min_s": 22.0,
        "max_s": 26.0,
    }
    assert summarize_green([]) is None


def test_pit_losses_accept_nan_for_missing_pit_times():
    nan = float("nan")
    laps = _race()
    for lap in laps:
        lap.setdefault("pit_in_time_ms", nan)
        lap.setdefault("pit_out_time_ms", nan)
    [stop] = pit_losses(laps, TOTAL)
    assert (stop.lap_in, stop.loss_s is not None) == (15, True)


def test_retirement_into_the_pits_is_not_a_stop():
    laps = _race(stop_in=29, n_laps=29)
    assert pit_losses(laps, TOTAL) == []
