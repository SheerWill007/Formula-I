"""
OpenF1 client — fetches live-feed metadata OpenF1 exposes for a session.

OpenF1's session_key is the same "Key" the official feed / FastF1 uses, so we
can look radio messages up with the session_key we already store in Postgres.

Endpoints used:
  - GET /v1/team_radio?session_key=X&driver_number=Y
"""

from __future__ import annotations
import json
import urllib.error
import urllib.parse
import urllib.request
import structlog

from ingestion.config import settings

log = structlog.get_logger()


def _clean_str(val):
    if val is None:
        return None
    s = str(val).strip()
    return None if s in ("", "nan", "None") else s


def fetch_team_radio(
    session_key: int,
    driver_number: int | None = None,
    base_url: str | None = None,
) -> list[dict]:
    """Fetch team radio messages for a session (optionally one driver).

    Returns a list of raw OpenF1 rows: {date, driver_number, recording_url, ...}.
    Best-effort: any HTTP/transport error returns [] and logs a warning so a
    flaky live feed never aborts an ingestion run.
    """
    query = urllib.parse.urlencode({"session_key": session_key})
    if driver_number is not None:
        query += f"&driver_number={driver_number}"
    url = f"{base_url or settings.openf1_base_url}/v1/team_radio?{query}"

    try:
        with urllib.request.urlopen(
            url, timeout=settings.openf1_timeout_seconds
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.warning("openf1.team_radio_failed", session_key=session_key, error=str(exc))
        return []

    rows = []
    for row in payload:
        date = _clean_str(row.get("date"))
        if not date:
            continue
        recording_url = _clean_str(row.get("recording_url"))
        if not recording_url:
            continue
        driver = row.get("driver_number")
        if driver is None:
            continue
        try:
            driver = int(driver)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "session_key": session_key,
                "driver_number": driver,
                "date": date,
                "recording_url": recording_url,
                "transcript": None,
            }
        )
    log.info("openf1.team_radio_fetched", session_key=session_key, count=len(rows))
    return rows


# ── Race timing: intervals, position changes, pit stops (OpenF1, 2023+) ──────
#
# OpenF1 has no data before 2023, so every fetcher returns [] for older
# sessions (or on any HTTP error) and ingestion carries on without it.


_MIN_REQUEST_GAP_S = 0.4  # OpenF1's free tier allows ~3 requests/second
_last_request_at = 0.0


def _throttle() -> None:
    import time

    global _last_request_at
    wait = _MIN_REQUEST_GAP_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


class OpenF1Error(RuntimeError):
    """A request failed after retries (as opposed to a successful empty answer)."""


class OpenF1Restricted(OpenF1Error):
    """OpenF1 answered 401: it blocks unauthenticated access, past sessions
    included, while a live F1 session is running. It lifts when the session
    ends, so callers should retry later rather than treat it as missing data."""


def _get_json(
    endpoint: str, params: dict, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    """GET ``/v1/<endpoint>`` with a few retries for 429/5xx and transport errors.

    OpenF1 answers 404 ``{"detail": "No results found."}`` for an empty result,
    which is a normal answer and always returns []. Any other failure returns []
    in the default best-effort mode, so a flaky live feed never aborts an
    ingestion run; with ``strict=True`` it raises :class:`OpenF1Error` instead,
    so callers that must not mistake an outage for "no data" can tell the two
    apart.
    """
    import time

    url = f"{base_url or settings.openf1_base_url}/v1/{endpoint}?" + urllib.parse.urlencode(
        params
    )
    last_error = "unknown error"
    for attempt in range(3):
        _throttle()
        try:
            with urllib.request.urlopen(
                url, timeout=settings.openf1_timeout_seconds * 3
            ) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload if isinstance(payload, list) else []
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return []
            last_error = f"HTTP {exc.code}"
            if exc.code == 401:
                # Not transient within this run: retrying only hammers the API.
                log.warning(
                    "openf1.access_restricted",
                    endpoint=endpoint,
                    hint="OpenF1 blocks unauthenticated access during a live "
                    "session; retry after it ends",
                )
                if strict:
                    raise OpenF1Restricted(
                        f"OpenF1 /{endpoint} is restricted (HTTP 401): a live "
                        "session is in progress"
                    ) from exc
                return []
            if exc.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        except Exception as exc:  # timeouts, connection resets, bad JSON
            last_error = str(exc)
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    log.warning("openf1.request_failed", endpoint=endpoint, error=last_error)
    if strict:
        raise OpenF1Error(f"OpenF1 /{endpoint} failed: {last_error}")
    return []


def _gap_parts(val) -> tuple[float | None, str | None]:
    """OpenF1 gaps are a number of seconds, null, or text like '+1 LAP'."""
    if val is None:
        return None, None
    if isinstance(val, (int, float)):
        return float(val), None
    s = str(val).strip()
    try:
        return float(s), None
    except ValueError:
        return None, s or None


def fetch_intervals(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    """Gap to leader and to the car ahead, ~every 4 s per driver."""
    rows = []
    for row in _get_json("intervals", {"session_key": session_key}, base_url, strict=strict):
        date, driver = _clean_str(row.get("date")), row.get("driver_number")
        if not date or driver is None:
            continue
        gap_s, gap_raw = _gap_parts(row.get("gap_to_leader"))
        int_s, int_raw = _gap_parts(row.get("interval"))
        rows.append(
            {
                "driver_number": int(driver),
                "date": date,
                "gap_to_leader_s": gap_s,
                "gap_to_leader_raw": gap_raw,
                "interval_s": int_s,
                "interval_raw": int_raw,
            }
        )
    log.info("openf1.intervals_fetched", session_key=session_key, count=len(rows))
    return rows


def fetch_positions(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    """Race order, one row each time a driver's position changes."""
    rows = []
    for row in _get_json("position", {"session_key": session_key}, base_url, strict=strict):
        date, driver, pos = (
            _clean_str(row.get("date")),
            row.get("driver_number"),
            row.get("position"),
        )
        if not date or driver is None or pos is None:
            continue
        rows.append({"driver_number": int(driver), "date": date, "position": int(pos)})
    log.info("openf1.positions_fetched", session_key=session_key, count=len(rows))
    return rows


def fetch_pit_stops(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    """Pit stops with lane duration in seconds.

    OpenF1 has used ``pit_duration`` and, later, ``lane_duration``; accept both.
    """
    rows = []
    for row in _get_json("pit", {"session_key": session_key}, base_url, strict=strict):
        driver, lap = row.get("driver_number"), row.get("lap_number")
        if driver is None or lap is None:
            continue
        duration = row.get("pit_duration", row.get("lane_duration"))
        rows.append(
            {
                "driver_number": int(driver),
                "lap_number": int(lap),
                "date": _clean_str(row.get("date")),
                "pit_duration_s": float(duration) if duration is not None else None,
            }
        )
    log.info("openf1.pit_fetched", session_key=session_key, count=len(rows))
    return rows


# ── Full-session fetchers (used by the OpenF1-only ingestion, openf1_ingest) ──
#
# These return OpenF1's rows unchanged; mapping to our schema lives in
# ``ingestion.openf1_ingest`` so it can be unit-tested without the network.


def fetch_meetings(
    year: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    return _get_json("meetings", {"year": year}, base_url, strict=strict)


def fetch_sessions(
    meeting_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    return _get_json("sessions", {"meeting_key": meeting_key}, base_url, strict=strict)


def fetch_drivers(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    return _get_json("drivers", {"session_key": session_key}, base_url, strict=strict)


def fetch_laps(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    return _get_json("laps", {"session_key": session_key}, base_url, strict=strict)


def fetch_stints(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    return _get_json("stints", {"session_key": session_key}, base_url, strict=strict)


def fetch_session_result(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    return _get_json("session_result", {"session_key": session_key}, base_url, strict=strict)


def fetch_starting_grid(session_key: int, base_url: str | None = None) -> list[dict]:
    # Not published for every session; [] is a normal answer.
    return _get_json("starting_grid", {"session_key": session_key}, base_url)


def fetch_race_control(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    return _get_json("race_control", {"session_key": session_key}, base_url, strict=strict)


def fetch_weather(
    session_key: int, base_url: str | None = None, *, strict: bool = False
) -> list[dict]:
    return _get_json("weather", {"session_key": session_key}, base_url, strict=strict)
