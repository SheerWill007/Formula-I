"""
Jolpica (Ergast successor) historical results.

Race and qualifying results back to 1950, used to extend model features
(driver/team/circuit history) beyond the FastF1 era. Results only: no
telemetry or laps.

Run it:

    uv run python -m ingestion.jolpica --start-year 2000 --end-year 2025

Jolpica's public API is rate limited (burst ~4 req/s, ~500 req/hour), and a
season needs ~10 paged requests, so a full 1950+ backfill must be spread over
several hours. The loader is an upsert, so re-running is safe and resumable.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import structlog

from ingestion.config import settings
from ingestion.loader import load_historical_results

log = structlog.get_logger()

PAGE_SIZE = 100  # Ergast/Jolpica max page size
REQUEST_GAP_S = 0.3  # stay under the burst limit


def _get(path: str, params: dict) -> dict:
    url = f"{settings.jolpica_base_url}/{path}.json?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            # Transient network trouble: same backoff as a throttled response.
            if attempt < 3:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def _paged_races(year: int, kind_path: str) -> list[dict]:
    """All races for a season. Jolpica paginates by result row, so merge
    pages that continue the same race."""
    races: dict[str, dict] = {}
    offset = 0
    while True:
        data = _get(f"{year}/{kind_path}", {"limit": PAGE_SIZE, "offset": offset})
        mr = data.get("MRData")
        if not isinstance(mr, dict) or "total" not in mr:
            # Never read a malformed answer as "zero races": that would log the
            # season as done with no rows, and a re-run would not retry it.
            raise RuntimeError(f"Jolpica response for {year}/{kind_path} has no MRData.total")
        for race in mr.get("RaceTable", {}).get("Races", []):
            key = race["round"]
            if key in races:
                for list_key in ("Results", "QualifyingResults"):
                    if list_key in race:
                        races[key].setdefault(list_key, []).extend(race[list_key])
            else:
                races[key] = race
        offset += PAGE_SIZE
        if offset >= int(mr["total"]):
            break
        time.sleep(REQUEST_GAP_S)
    return list(races.values())


def _int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _float(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _race_date(val) -> date | None:
    try:
        return date.fromisoformat(val)
    except (TypeError, ValueError):
        return None


def _base(race: dict, kind: str, entry: dict) -> dict:
    circuit = race.get("Circuit", {})
    driver = entry.get("Driver", {})
    constructor = entry.get("Constructor", {})
    return {
        "year": int(race["season"]),
        "round": int(race["round"]),
        "kind": kind,
        "race_name": race.get("raceName"),
        "circuit_id": circuit.get("circuitId"),
        "circuit_name": circuit.get("circuitName"),
        "country": circuit.get("Location", {}).get("country"),
        "race_date": _race_date(race.get("date")),
        "driver_id": driver.get("driverId"),
        "driver_code": driver.get("code"),
        "driver_name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
        or None,
        "constructor_id": constructor.get("constructorId"),
        "constructor_name": constructor.get("name"),
        "grid": None,
        "position": _int(entry.get("position")),
        "position_text": entry.get("positionText"),
        "points": None,
        "laps": None,
        "status": None,
        "q1": None,
        "q2": None,
        "q3": None,
    }


def parse_race_results(races: list[dict]) -> list[dict]:
    rows = []
    for race in races:
        for entry in race.get("Results", []):
            row = _base(race, "R", entry)
            row.update(
                grid=_int(entry.get("grid")),
                points=_float(entry.get("points")),
                laps=_int(entry.get("laps")),
                status=entry.get("status"),
            )
            if row["driver_id"]:
                rows.append(row)
    return rows


def parse_qualifying_results(races: list[dict]) -> list[dict]:
    rows = []
    for race in races:
        for entry in race.get("QualifyingResults", []):
            row = _base(race, "Q", entry)
            row.update(q1=entry.get("Q1") or None, q2=entry.get("Q2") or None,
                       q3=entry.get("Q3") or None)
            if row["driver_id"]:
                rows.append(row)
    return rows


def backfill_year(year: int) -> int:
    rows = parse_race_results(_paged_races(year, "results"))
    time.sleep(REQUEST_GAP_S)
    # Qualifying data only exists from 1994 in Ergast; earlier years return none.
    if year >= 1994:
        rows += parse_qualifying_results(_paged_races(year, "qualifying"))
    count = load_historical_results(rows)
    log.info("jolpica.year_done", year=year, rows=count)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Jolpica historical results")
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    args = parser.parse_args(argv)
    if args.start_year > args.end_year:
        parser.error("--start-year must not be later than --end-year")

    total = 0
    for year in range(args.start_year, args.end_year + 1):
        try:
            total += backfill_year(year)
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                # Still throttled after the retries: the hourly quota is spent, so
                # carrying on would only burn through the remaining years. Stop
                # with a non-zero status; re-running is safe (the loader upserts).
                log.error("jolpica.quota_exhausted", year=year, error=str(exc))
                print(json.dumps({"rows": total, "stopped_at_year": year}))
                return 1
            # Keep going: the upsert makes a later re-run fill any gap.
            log.error("jolpica.year_failed", year=year, error=str(exc))
        time.sleep(REQUEST_GAP_S)
    print(json.dumps({"rows": total}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
