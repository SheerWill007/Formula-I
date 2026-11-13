import pandas as pd

from ingestion.fastf1_client import extract_session_results, extract_track_status
from ingestion.jolpica import parse_qualifying_results, parse_race_results
from ingestion.openf1_client import _gap_parts


class _Session:
    def __init__(self, laps=None, track_status=None, results=None):
        self.laps = laps
        self.track_status = track_status
        self.results = results


def test_track_status_builds_closed_periods_with_laps():
    laps = pd.DataFrame(
        {
            "LapNumber": [1, 2, 3, 1, 2, 3],
            "LapStartTime": pd.to_timedelta([0, 90, 180, 1, 91, 181], unit="s"),
        }
    )
    ts = pd.DataFrame(
        {
            "Time": pd.to_timedelta([0, 100, 150], unit="s"),
            "Status": ["1", "4", "1"],
            "Message": ["AllClear", "SCDeployed", "AllClear"],
        }
    )
    rows = extract_track_status(_Session(laps=laps, track_status=ts), 7)
    assert [r["status_label"] for r in rows] == ["AllClear", "SafetyCar", "AllClear"]
    assert rows[1]["start_ms"] == 100_000 and rows[1]["end_ms"] == 150_000
    assert rows[1]["start_lap"] == 2 and rows[1]["end_lap"] == 2
    assert rows[2]["end_ms"] is None and rows[2]["end_lap"] is None


def test_track_status_empty_returns_empty():
    assert extract_track_status(_Session(track_status=pd.DataFrame()), 1) == []


def test_session_results_handles_nan_and_missing_columns():
    res = pd.DataFrame(
        {
            "DriverNumber": ["1", "44"],
            "Abbreviation": ["VER", "HAM"],
            "TeamName": ["Red Bull Racing", "Ferrari"],
            "GridPosition": [1.0, float("nan")],
            "Position": [1.0, 2.0],
            "Status": ["Finished", "Lapped"],
            "Points": [25.0, 18.0],
            "Time": pd.to_timedelta([5400, None], unit="s"),
        }
    )
    rows = extract_session_results(_Session(results=res), 9)
    assert rows[0]["grid_position"] == 1 and rows[0]["race_time_ms"] == 5_400_000
    assert rows[1]["grid_position"] is None and rows[1]["race_time_ms"] is None
    assert rows[0]["q1_ms"] is None  # column absent in this fixture


def test_gap_parts_numbers_text_and_null():
    assert _gap_parts(1.234) == (1.234, None)
    assert _gap_parts("2.5") == (2.5, None)
    assert _gap_parts("+1 LAP") == (None, "+1 LAP")
    assert _gap_parts(None) == (None, None)


_RACE = {
    "season": "2023",
    "round": "1",
    "raceName": "Bahrain Grand Prix",
    "date": "2023-03-05",
    "Circuit": {
        "circuitId": "bahrain",
        "circuitName": "Bahrain International Circuit",
        "Location": {"country": "Bahrain"},
    },
    "Results": [
        {
            "position": "1",
            "positionText": "1",
            "points": "25",
            "grid": "1",
            "laps": "57",
            "status": "Finished",
            "Driver": {"driverId": "max_verstappen", "code": "VER",
                       "givenName": "Max", "familyName": "Verstappen"},
            "Constructor": {"constructorId": "red_bull", "name": "Red Bull"},
        }
    ],
    "QualifyingResults": [
        {
            "position": "1", "Q1": "1:32.0", "Q2": "1:31.0", "Q3": "",
            "Driver": {"driverId": "max_verstappen", "code": "VER",
                       "givenName": "Max", "familyName": "Verstappen"},
            "Constructor": {"constructorId": "red_bull", "name": "Red Bull"},
        }
    ],
}


def test_jolpica_race_and_quali_parsing():
    race = parse_race_results([_RACE])[0]
    assert (race["year"], race["round"], race["kind"]) == (2023, 1, "R")
    assert race["grid"] == 1 and race["points"] == 25.0
    assert race["driver_name"] == "Max Verstappen"
    quali = parse_qualifying_results([_RACE])[0]
    assert quali["kind"] == "Q" and quali["q3"] is None and quali["q1"] == "1:32.0"
