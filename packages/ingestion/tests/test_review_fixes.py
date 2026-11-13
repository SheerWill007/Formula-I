import io
import urllib.error

import httpx
import pytest

from ingestion import fia_documents, jolpica, openf1_client
from ingestion import openf1_ingest as oi
from ingestion.documents import DocumentError


# ── OpenF1: failure vs empty ─────────────────────────────────────────────────


def _http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(openf1_client, "_throttle", lambda: None)


def test_404_is_an_empty_answer_even_in_strict_mode(monkeypatch):
    monkeypatch.setattr(openf1_client.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(_http_error(404)))
    assert openf1_client._get_json("laps", {}, strict=True) == []


def test_strict_raises_after_retries_but_default_stays_best_effort(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise TimeoutError("timed out")

    monkeypatch.setattr(openf1_client.urllib.request, "urlopen", boom)
    assert openf1_client._get_json("laps", {}) == []  # best effort: swallowed
    assert len(calls) == 3  # transport errors are retried, not given up on at once
    with pytest.raises(openf1_client.OpenF1Error):
        openf1_client._get_json("laps", {}, strict=True)


def test_strict_http_500_retries_then_raises(monkeypatch):
    n = []
    monkeypatch.setattr(
        openf1_client.urllib.request, "urlopen",
        lambda *a, **k: (n.append(1), (_ for _ in ()).throw(_http_error(503)))[1],
    )
    with pytest.raises(openf1_client.OpenF1Error):
        openf1_client._get_json("stints", {}, strict=True)
    assert len(n) == 3


# ── race-control deletions ───────────────────────────────────────────────────


def _lap(drv, n, start, dur):
    return {"driver_number": drv, "lap_number": n, "date_start": start, "lap_duration": dur}


def test_each_deletion_message_removes_exactly_one_lap():
    # Two laps with the same time; only one deletion message -> only one deleted.
    laps = {1: [_lap(1, 3, "2024-05-26T13:10:00+00:00", 91.0), _lap(1, 7, "2024-05-26T13:20:00+00:00", 91.0)]}
    rc = [{"date": "2024-05-26T13:21:40+00:00", "message": "CAR 1 (AAA) TIME 1:31.000 DELETED - TRACK LIMITS AT TURN 4"}]
    assert list(oi.match_deletions(rc, laps)) == [(1, 7)]  # the lap that just ended, not both


def test_two_messages_for_the_same_time_delete_two_laps():
    laps = {1: [_lap(1, 3, "2024-05-26T13:10:00+00:00", 91.0), _lap(1, 7, "2024-05-26T13:20:00+00:00", 91.0)]}
    msg = "CAR 1 (AAA) TIME 1:31.000 DELETED - TRACK LIMITS AT TURN 4"
    rc = [{"date": "2024-05-26T13:11:40+00:00", "message": msg},
          {"date": "2024-05-26T13:21:40+00:00", "message": msg}]
    assert sorted(oi.match_deletions(rc, laps)) == [(1, 3), (1, 7)]


def test_deletion_with_no_matching_lap_is_ignored():
    laps = {1: [_lap(1, 3, "2024-05-26T13:10:00+00:00", 95.5)]}
    rc = [{"date": "2024-05-26T13:11:40+00:00", "message": "CAR 1 (AAA) TIME 1:31.000 DELETED - TRACK LIMITS"}]
    assert oi.match_deletions(rc, laps) == {}


# ── FIA documents ────────────────────────────────────────────────────────────


def test_fia_main_requires_approve_before_any_network(monkeypatch, tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text("[]")
    monkeypatch.setattr(fia_documents.httpx, "Client", lambda *a, **k: pytest.fail("fetched without approval"))
    with pytest.raises(SystemExit) as exc:
        fia_documents.main(["--manifest", str(manifest)])
    assert exc.value.code == 2


def _client_returning(body: bytes):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=body)))


def test_fetch_pdf_accepts_a_pdf():
    assert fia_documents.fetch_pdf(_client_returning(b"%PDF-1.7 ..."), "https://x/y.pdf").startswith(b"%PDF")


def test_fetch_pdf_rejects_non_pdf_and_oversize(monkeypatch):
    with pytest.raises(DocumentError, match="did not return a PDF"):
        fia_documents.fetch_pdf(_client_returning(b"<html>"), "https://x/y.pdf")
    monkeypatch.setattr(fia_documents, "MAX_PDF_BYTES", 10)
    with pytest.raises(DocumentError, match="larger than"):
        fia_documents.fetch_pdf(_client_returning(b"%PDF" + b"0" * 50), "https://x/y.pdf")


# ── Jolpica ──────────────────────────────────────────────────────────────────


def test_paged_races_merges_pages_of_the_same_round(monkeypatch):
    pages = [
        {"MRData": {"total": "101", "RaceTable": {"Races": [{"round": "1", "Results": [{"Driver": {"driverId": "hamilton"}}]}]}}},
        {"MRData": {"total": "101", "RaceTable": {"Races": [{"round": "1", "Results": [{"Driver": {"driverId": "verstappen"}}]}]}}},
    ]
    offsets = []

    def fake_get(path, params):
        offsets.append(params["offset"])
        return pages[len(offsets) - 1]

    monkeypatch.setattr(jolpica, "_get", fake_get)
    races = jolpica._paged_races(2024, "results")
    assert offsets == [0, 100] and len(races) == 1
    assert [r["Driver"]["driverId"] for r in races[0]["Results"]] == ["hamilton", "verstappen"]


def test_malformed_jolpica_response_fails_the_season(monkeypatch):
    monkeypatch.setattr(jolpica, "_get", lambda path, params: {"oops": 1})
    with pytest.raises(RuntimeError, match="MRData.total"):
        jolpica._paged_races(2024, "results")


def test_jolpica_retries_network_errors(monkeypatch):
    attempts = []

    def flaky(url, timeout):
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.URLError("connection reset")
        return io.BytesIO(b'{"MRData": {}}')

    monkeypatch.setattr(jolpica.urllib.request, "urlopen", flaky)
    assert jolpica._get("2024/results", {}) == {"MRData": {}}
    assert len(attempts) == 3


def test_reversed_year_range_is_an_argument_error():
    with pytest.raises(SystemExit) as exc:
        jolpica.main(["--start-year", "2025", "--end-year", "2020"])
    assert exc.value.code == 2


def test_persistent_429_stops_the_backfill_with_nonzero_exit(monkeypatch, capsys):
    years = []

    def fake_backfill(year):
        years.append(year)
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(b""))

    monkeypatch.setattr(jolpica, "backfill_year", fake_backfill)
    assert jolpica.main(["--start-year", "2020", "--end-year", "2024"]) == 1
    assert years == [2020]  # did not carry on through 2021-2024 while throttled
    assert "stopped_at_year" in capsys.readouterr().out


def test_other_year_errors_are_skipped_and_the_run_continues(monkeypatch):
    years = []

    def fake_backfill(year):
        years.append(year)
        if year == 2021:
            raise RuntimeError("boom")
        return 5

    monkeypatch.setattr(jolpica, "backfill_year", fake_backfill)
    assert jolpica.main(["--start-year", "2020", "--end-year", "2022"]) == 0
    assert years == [2020, 2021, 2022]
