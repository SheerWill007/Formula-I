import json

import pytest

from backend.f1lab.report import (
    degradation_by_stint,
    degradation_chart,
    format_race_summary,
    gaps_to_car_ahead,
    pit_summary,
    race_summary,
)

TOTAL = 57


def _stint_laps(stint, first, n, deg, fuel=0.05, compound="SOFT"):
    return [
        {
            "lap_number": lap,
            "lap_time_ms": round(
                (95.0 + deg * (lap - first) + fuel * (TOTAL - lap)) * 1000
            ),
            "stint": stint,
            "compound": compound,
        }
        for lap in range(first, first + n)
    ]


def test_degradation_by_stint_recovers_each_stints_true_slope():
    laps = _stint_laps(1, 2, 15, 0.04, compound="MEDIUM") + _stint_laps(2, 20, 25, 0.10)
    first, second = degradation_by_stint(laps, TOTAL)
    assert (first.stint, first.compound, second.compound) == (1, "MEDIUM", "SOFT")
    assert first.corrected_slope_s_per_lap == pytest.approx(0.04, abs=1e-3)
    assert second.corrected_slope_s_per_lap == pytest.approx(0.10, abs=1e-3)
    assert first.raw_slope_s_per_lap == pytest.approx(-0.01, abs=1e-3)  # fuel hides it
    assert second.r2 > 0.99 and second.issues == ()


def test_short_stints_are_skipped_and_implausible_ones_are_flagged():
    laps = _stint_laps(1, 2, 3, 0.04) + _stint_laps(2, 10, 20, -0.2)
    results = degradation_by_stint(laps, TOTAL)
    assert [r.stint for r in results] == [2]
    assert results[0].issues == ("deg_negative_corrected",)


def test_chart_is_json_serialisable_with_a_scatter_and_a_fit_per_stint():
    laps = _stint_laps(1, 2, 15, 0.04) + _stint_laps(2, 20, 25, 0.10)
    option = degradation_chart(laps, TOTAL)
    json.dumps(option)
    assert [s["type"] for s in option["series"]] == [
        "scatter",
        "line",
        "scatter",
        "line",
    ]


def test_chart_with_no_usable_stint_has_no_series():
    assert degradation_chart(_stint_laps(1, 2, 3, 0.04), TOTAL)["series"] == []


def _driver(stop_in, extra_s):
    laps = []
    for lap in range(2, 40):
        t = (
            95.0
            + 0.05 * (TOTAL - lap)
            + (extra_s if lap in (stop_in, stop_in + 1) else 0)
        )
        row = {
            "lap_number": lap,
            "lap_time_ms": round(t * 1000),
            "stint": 1 if lap <= stop_in else 2,
        }
        if lap == stop_in:
            row["pit_in_time_ms"] = 1
        if lap == stop_in + 1:
            row["pit_out_time_ms"] = 1
        laps.append(row)
    return laps


def test_pit_summary_lists_stops_and_summarises_green_ones():
    summary = pit_summary({"HAM": _driver(15, 11.0), "LEC": _driver(20, 12.0)}, TOTAL)
    assert [(s["driver"], s["lap_in"]) for s in summary["stops"]] == [
        ("HAM", 15),
        ("LEC", 20),
    ]
    assert summary["stops"][0]["loss_s"] == pytest.approx(22.0, abs=0.01)
    assert summary["green"]["n"] == 2 and summary["green"]["median_s"] == pytest.approx(
        23.0, abs=0.01
    )
    json.dumps(summary)


def _car(number, position, base, stop_in=None, n=30, deleted=()):
    laps = []
    for lap in range(1, n + 1):
        t = base + (12.0 if stop_in and lap in (stop_in, stop_in + 1) else 0)
        row = {
            "driver_number": number,
            "lap_number": lap,
            "lap_time_ms": round(t * 1000),
            "position": position,
            "stint": 1 if not stop_in or lap <= stop_in else 2,
            "compound": "SOFT" if not stop_in or lap <= stop_in else "HARD",
            "deleted": lap in deleted,
        }
        if stop_in == lap:
            row["pit_in_time_ms"] = 1
        if stop_in and lap == stop_in + 1:
            row["pit_out_time_ms"] = 1
        laps.append(row)
    return laps


def test_gap_comes_from_summed_lap_times_and_counts_deleted_laps():
    laps = _car(1, 1, 90.0) + _car(2, 2, 90.1, deleted=(5,))
    gaps = gaps_to_car_ahead(laps)
    assert gaps[(2, 10)] == pytest.approx(1.0, abs=0.01)
    assert (1, 10) not in gaps  # the leader has nobody ahead


def test_a_missing_lap_time_stops_the_gap_rather_than_inventing_one():
    laps = _car(1, 1, 90.0) + _car(2, 2, 90.1)
    laps[30 + 4]["lap_time_ms"] = None  # driver 2, lap 5
    gaps = gaps_to_car_ahead(laps)
    assert (2, 4) in gaps and (2, 5) not in gaps and (2, 20) not in gaps


def test_race_summary_gives_order_stops_and_traffic():
    laps = _car(1, 1, 90.0, stop_in=15) + _car(2, 2, 90.01, stop_in=20)
    summary = race_summary(laps, {1: "AAA", 2: "BBB"})
    first, second = summary["drivers"]
    assert summary["race_laps"] == 30
    assert (first["driver"], first["final_position"], first["laps"]) == ("AAA", 1, 30)
    assert first["compounds"] == ["SOFT", "HARD"]
    assert (
        first["stops"][0]["lap_in"] == 15 and first["stops"][0]["position_before"] == 1
    )
    assert second["clean_laps_in_traffic"] > 0
    assert second["clean_laps_with_gap"] > 0
    assert first["clean_laps_in_traffic"] == 0
    assert "P2 BBB 30L gap ahead 0.3s S>H" in format_race_summary(summary)


def test_retired_driver_sorts_after_finishers():
    laps = _car(1, 1, 90.0, n=10) + _car(2, 2, 90.0)
    assert [
        r["driver"] for r in race_summary(laps, {1: "OUT", 2: "FIN"})["drivers"]
    ] == [
        "FIN",
        "OUT",
    ]


def test_unknown_gaps_are_reported_as_unknown_not_as_clean_air():
    laps = _car(1, 1, 90.0) + _car(2, 2, 90.01)
    laps[30]["lap_time_ms"] = None  # driver 2 has no gap from lap 1 on
    summary = race_summary(laps, {1: "AAA", 2: "BBB"})
    assert summary["drivers"][1]["clean_laps_with_gap"] == 0
    assert "traffic unknown" in format_race_summary(summary).splitlines()[2]


def test_red_flag_and_missing_time_stops_are_listed_without_a_loss():
    laps = _car(1, 1, 90.0, stop_in=5)
    laps[4]["track_status"] = "125"
    laps[5]["lap_time_ms"] = None
    [stop] = race_summary(laps, {1: "AAA"})["drivers"][0]["stops"]
    assert (stop["lap_in"], stop["condition"], stop["loss_s"]) == (5, "red", None)


def test_full_names_appear_so_codes_are_not_guessed():
    summary = race_summary(_car(12, 1, 90.0), {12: "ANT"}, {12: "Kimi Antonelli"})
    assert "P1 ANT (Kimi Antonelli) 30L" in format_race_summary(summary)


def test_final_gap_is_shown_and_unknown_when_a_lap_time_is_missing():
    laps = _car(1, 1, 90.0) + _car(2, 2, 90.1)
    summary = race_summary(laps, {1: "AAA", 2: "BBB"})
    assert summary["drivers"][1]["final_gap_ahead_s"] == pytest.approx(3.0)
    assert "gap ahead 3.0s" in format_race_summary(summary)
    laps[30]["lap_time_ms"] = None
    assert "gap ahead unknown" in format_race_summary(
        race_summary(laps, {1: "AAA", 2: "BBB"})
    )
