from datetime import datetime, timedelta, timezone

from ingestion import openf1_ingest as oi

T0 = datetime(2024, 5, 26, 13, 0, tzinfo=timezone.utc)


def at(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat()


def test_stint_for_lap_handles_monaco_red_flag_stints():
    # OpenF1 Monaco 2024: stint 1 = laps 1-0 (degenerate), stint 2 = laps 1-78
    stints = [
        {"stint_number": 1, "lap_start": 1, "lap_end": 0, "compound": "MEDIUM", "tyre_age_at_start": 0},
        {"stint_number": 2, "lap_start": 1, "lap_end": 78, "compound": "HARD", "tyre_age_at_start": 0},
    ]
    assert oi.stint_for_lap(stints, 1)["compound"] == "HARD"
    assert oi.stint_for_lap(stints, 40)["stint_number"] == 2
    assert oi.stint_for_lap(stints, 79) is None


def test_stint_for_lap_open_ended_and_normal_stops():
    stints = [
        {"stint_number": 1, "lap_start": 1, "lap_end": 17},
        {"stint_number": 2, "lap_start": 18, "lap_end": None},
    ]
    assert oi.stint_for_lap(stints, 17)["stint_number"] == 1
    assert oi.stint_for_lap(stints, 18)["stint_number"] == 2
    assert oi.stint_for_lap(stints, 60)["stint_number"] == 2


def _rc(sec, msg, flag=None, scope=None, lap=1, cat="Other"):
    return {"date": at(sec), "message": msg, "flag": flag, "scope": scope,
            "lap_number": lap, "category": cat}


def test_red_flag_period_closes_on_restart_not_pit_exit_light():
    rc = [
        _rc(0, "GREEN LIGHT - PIT EXIT OPEN", "GREEN", "Track"),  # before the race
        _rc(60, "RED FLAG", "RED", "Track"),
        _rc(900, "GREEN LIGHT - PIT EXIT OPEN", "GREEN", "Track", lap=1),  # must NOT close red
        _rc(2400, "SESSION STARTED", cat="SessionStatus", lap=2),
    ]
    periods = oi.derive_incident_periods(rc, None)
    assert [(p["label"], p["start_lap"], p["end_lap"]) for p in periods] == [("Red", 1, 2)]
    assert periods[0]["end"] == T0 + timedelta(seconds=2400)


def test_safety_car_then_vsc_do_not_overlap():
    rc = [
        _rc(100, "SAFETY CAR DEPLOYED", cat="SafetyCar", lap=3),
        _rc(400, "SAFETY CAR IN THIS LAP", cat="SafetyCar", lap=6),
        _rc(800, "VIRTUAL SAFETY CAR DEPLOYED", cat="SafetyCar", lap=10),
        _rc(900, "VIRTUAL SAFETY CAR ENDING", cat="SafetyCar", lap=11),
    ]
    p = oi.derive_incident_periods(rc, None)
    assert [x["label"] for x in p] == ["SafetyCar", "VirtualSafetyCar"]
    assert p[0]["end"] <= p[1]["start"]


def test_clean_race_still_produces_all_clear_row():
    # The empirical SC rate counts a race only if it has rows, so a clean race
    # must not produce an empty list.
    rows = oi.build_track_status_rows([], T0, [(1, T0), (2, T0 + timedelta(seconds=90))], 7)
    assert [(r["status_label"], r["end_ms"]) for r in rows] == [("AllClear", None)]


def test_track_status_rows_fill_gaps_with_all_clear():
    inc = [{"code": "4", "label": "SafetyCar", "start": T0 + timedelta(seconds=100),
            "end": T0 + timedelta(seconds=200), "start_lap": 2, "end_lap": 3}]
    rows = oi.build_track_status_rows(inc, T0, [(1, T0)], 7)
    assert [r["status_label"] for r in rows] == ["AllClear", "SafetyCar", "AllClear"]
    assert rows[1]["start_ms"] == 100_000 and rows[1]["start_lap"] == 2
    assert rows[2]["start_lap"] == 3 and rows[2]["end_ms"] is None


def test_results_status_vocabulary_and_race_time_semantics():
    drivers = [{"driver_number": n, "abbreviation": a, "team_name": "T"} for n, a in
               [(1, "AAA"), (2, "BBB"), (3, "CCC"), (4, "DDD"), (5, "EEE")]]
    results = [
        {"driver_number": 1, "position": 1, "number_of_laps": 57, "duration": 5400.0, "gap_to_leader": 0, "points": 25},
        {"driver_number": 2, "position": 2, "number_of_laps": 57, "duration": 5410.5, "gap_to_leader": 10.5, "points": 18},
        {"driver_number": 3, "position": 3, "number_of_laps": 56, "gap_to_leader": "+1 LAP", "points": 15},
        {"driver_number": 4, "position": None, "number_of_laps": 12, "dnf": True},
        {"driver_number": 5, "position": None, "number_of_laps": 0, "dns": True},
    ]
    rows = {r["driver_number"]: r for r in oi.build_session_results(results, drivers, [], "R", 9)}
    assert rows[1]["race_time_ms"] == 5_400_000.0  # winner: total time
    assert rows[2]["race_time_ms"] == 10_500.0  # others: gap to winner (FastF1 semantics)
    assert rows[3]["race_time_ms"] is None and rows[3]["status"] == "+1 Lap"
    assert rows[4]["status"] == "Retired" and rows[4]["classified_position"] == "R"
    assert rows[5]["status"] == "Did not start"  # excluded from DNF-rate by the feature SQL


def test_quali_results_split_q1_q2_q3():
    drivers = [{"driver_number": 1, "abbreviation": "AAA", "team_name": "T"}]
    res = [{"driver_number": 1, "position": 1, "duration": [90.0, 89.5, None]}]
    row = oi.build_session_results(res, drivers, [], "Q", 9)[0]
    assert (row["q1_ms"], row["q2_ms"], row["q3_ms"]) == (90_000.0, 89_500.0, None)
    assert row["race_time_ms"] is None


def _lap(drv, n, start_s, dur, **kw):
    return {"driver_number": drv, "lap_number": n, "date_start": at(start_s), "lap_duration": dur,
            "duration_sector_1": 30.0, "duration_sector_2": 30.0, "duration_sector_3": dur - 60 if dur else None,
            "i1_speed": 300, "st_speed": 320, "is_pit_out_lap": False, **kw}


def test_build_laps_derives_compound_tyre_life_pit_markers_pb_and_deletions():
    laps = [_lap(1, 1, 0, None, is_pit_out_lap=True), _lap(1, 2, 100, 92.0), _lap(1, 3, 192, 91.0),
            _lap(1, 4, 283, 95.0), _lap(1, 5, 378, 99.0, is_pit_out_lap=True)]
    stints = [{"driver_number": 1, "stint_number": 1, "lap_start": 1, "lap_end": 4, "compound": "SOFT", "tyre_age_at_start": 2},
              {"driver_number": 1, "stint_number": 2, "lap_start": 5, "lap_end": None, "compound": "HARD", "tyre_age_at_start": 0}]
    pits = [{"driver_number": 1, "lap_number": 4, "date": at(370)}]
    positions = [{"driver_number": 1, "date": at(0), "position": 3}, {"driver_number": 1, "date": at(200), "position": 2}]
    rc = [{"date": at(285), "message": "CAR 1 (AAA) TIME 1:31.000 DELETED - TRACK LIMITS AT TURN 4", "lap_number": 3}]
    rows = {r["lap_number"]: r for r in
            oi.build_laps(laps, stints, pits, positions, [], rc, T0, "R", 9)}
    assert rows[2]["compound"] == "SOFT" and rows[2]["tyre_life_laps"] == 2 + (2 - 1) + 1
    assert rows[2]["fresh_tyre"] is False and rows[5]["fresh_tyre"] is True
    assert rows[4]["pit_in_time_ms"] == 370_000.0 and rows[5]["pit_out_time_ms"] == 370_000.0
    assert rows[3]["deleted"] is True and "TRACK LIMITS" in rows[3]["deleted_reason"]
    assert rows[3]["is_personal_best"] is False  # deleted laps never count
    assert rows[2]["is_personal_best"] is True
    assert rows[2]["position"] == 3 and rows[3]["position"] == 2  # position at end of lap
    assert rows[1]["lap_time_ms"] is None and rows[1]["is_accurate"] is False


def test_quali_segment_follows_qualifying_phase_events():
    laps = [_lap(1, 1, 10, 90.0), _lap(1, 2, 700, 90.0)]
    rc = [{"date": at(0), "qualifying_phase": 1, "message": "GREEN LIGHT - PIT EXIT OPEN"},
          {"date": at(600), "qualifying_phase": 2, "message": "GREEN LIGHT - PIT EXIT OPEN"}]
    rows = {r["lap_number"]: r for r in oi.build_laps(laps, [], [], [], [], rc, T0, "Q", 9)}
    assert (rows[1]["quali_segment"], rows[2]["quali_segment"]) == (1, 2)


def test_pick_meeting_exact_partial_and_ambiguous():
    ms = [{"meeting_name": n, "meeting_key": i} for i, n in enumerate(
        ["Pre-Season Testing", "Bahrain Grand Prix", "Italian Grand Prix", "Emilia Romagna Grand Prix"])]
    assert oi.pick_meeting(ms, "bahrain")["meeting_name"] == "Bahrain Grand Prix"
    assert oi.pick_meeting(ms, "Italian Grand Prix")["meeting_name"] == "Italian Grand Prix"
    assert oi.pick_meeting(ms, "Grand Prix") is None  # ambiguous -> no guess
    assert oi.pick_meeting(ms, "Testing") is None  # testing is never a race weekend


def test_session_info_maps_names_and_skips_cancelled():
    meeting = {"meeting_name": "Chinese Grand Prix", "country_name": "China"}
    sess = {"session_key": 5, "year": 2025, "session_name": "Sprint Qualifying", "date_start": at(0)}
    assert oi.build_session_info(meeting, sess)["session_type"] == "SQ"
    assert oi.build_session_info(meeting, {**sess, "is_cancelled": True}) is None
    assert oi.build_session_info(meeting, {**sess, "session_name": "Day 1"}) is None


def test_401_is_reported_as_restricted_without_retrying(monkeypatch):
    import io
    import urllib.error

    import pytest

    from ingestion import openf1_client as of1

    calls = {"n": 0}

    def deny(*_a, **_k):
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(of1.urllib.request, "urlopen", deny)
    monkeypatch.setattr(of1, "_throttle", lambda: None)

    with pytest.raises(of1.OpenF1Restricted):
        of1._get_json("meetings", {"year": 2026}, strict=True)
    assert calls["n"] == 1
    assert of1._get_json("meetings", {"year": 2026}) == []


def test_cli_reports_restriction_instead_of_a_traceback(monkeypatch, capsys):
    from ingestion import openf1_client as of1
    from ingestion import openf1_ingest

    def blocked(*_a, **_k):
        raise of1.OpenF1Restricted("OpenF1 /meetings is restricted (HTTP 401)")

    monkeypatch.setattr(openf1_ingest, "ingest_session_openf1", blocked)
    code = openf1_ingest.main(["--year", "2026", "--gp", "Mexico City", "--session", "Q"])
    assert code == 2
    assert "Retry after the session ends" in capsys.readouterr().out
