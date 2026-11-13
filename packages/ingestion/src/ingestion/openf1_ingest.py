"""
OpenF1-only session ingestion: the FastF1-free path.

F1's livetiming static feed (which FastF1 reads) now rejects unauthenticated
requests, so sessions that are not already in the local FastF1 cache cannot be
ingested with FastF1 without an F1TV login. OpenF1 (2023+) is free and carries
enough to fill the same tables:

    sessions, drivers, lap_times, session_results, race_control_events,
    weather_events, track_status_periods, team_radio, session_intervals,
    position_changes, pit_stops

Differences from the FastF1 path, on purpose and worth knowing:

* No car telemetry (speed/throttle/brake traces). OpenF1 has ``car_data`` and
  ``location`` but they are large; they are not ingested here.
* ``lap_times`` fields OpenF1 does not give are derived: compound / stint /
  tyre life from stints, position from position changes, personal best from
  running minima, track limits deletions from race-control messages, quali
  segment from ``qualifying_phase``. ``is_accurate`` is an approximation.
* ``track_status_periods`` holds safety car, VSC and red flag periods (from
  race-control messages) plus AllClear between them. Yellow flags are not
  tracked, and times are ms since the OpenF1 session start.
* ``grid_position`` is only filled when OpenF1 publishes a starting grid.
* ``session_results.position`` is NULL for retirements (OpenF1 does not rank them;
  FastF1 orders them by laps completed).

Run it:

    uv run python -m ingestion.openf1_ingest --year 2024 --gp Bahrain --session R
    uv run python -m ingestion.openf1_ingest --year 2024 --all     # every missing session

A session that already has laps in the database is skipped unless ``--force``,
so this never overwrites richer FastF1 data.
"""

from __future__ import annotations

import argparse
import bisect
import re
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import text

from ingestion import openf1_client as of1
from ingestion.loader import (
    _get_engine,
    load_drivers,
    load_laps,
    load_pit_stops,
    load_position_changes,
    load_race_control,
    load_session_intervals,
    load_session_results,
    load_team_radio,
    load_track_status,
    load_weather_events,
    update_session_weather,
    upsert_session,
)

log = structlog.get_logger()

# OpenF1 session_name -> our session_type code (mirrors ingest_session.NAME_TO_CODE)
NAME_TO_CODE = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Sprint": "SS",
    "Race": "R",
}
CODE_ALIASES = {"S": "SS"}  # the CLI/Makefile also use "S" for the sprint
RACE_LIKE = {"R", "SS"}
QUALI_LIKE = {"Q", "SQ"}

_DELETED_RE = re.compile(
    r"CAR (?P<num>\d+) \([A-Z]{3}\) TIME (?P<time>\d+:\d{2}\.\d{3}) DELETED - (?P<why>.+)",
    re.IGNORECASE,
)


# ── small helpers ─────────────────────────────────────────────────────────────


def _dt(value) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _ms(seconds) -> float | None:
    try:
        return None if seconds is None else float(seconds) * 1000.0
    except (TypeError, ValueError):
        return None


def _lap_time_text_to_ms(txt: str) -> float:
    minutes, rest = txt.split(":")
    return (int(minutes) * 60 + float(rest)) * 1000.0


def _at(sorted_times: list[datetime], values: list, ts: datetime):
    """Value of the latest entry whose time is <= ts (None if ts precedes all)."""
    i = bisect.bisect_right(sorted_times, ts) - 1
    return values[i] if i >= 0 else None


# ── session lookup ────────────────────────────────────────────────────────────


def build_session_info(meeting: dict, sess: dict) -> dict | None:
    code = NAME_TO_CODE.get(sess.get("session_name"))
    if code is None or sess.get("is_cancelled"):
        return None
    return {
        "session_key": int(sess["session_key"]),
        "year": int(sess["year"]),
        "gp_name": meeting["meeting_name"],
        "country": sess.get("country_name") or meeting.get("country_name"),
        "session_type": code,
        "session_name": sess["session_name"],
        "date_start": sess.get("date_start"),
    }


def pick_meeting(meetings: list[dict], gp: str) -> dict | None:
    """Match a GP by name: exact first, then a unique case-insensitive substring."""
    wanted = gp.strip().casefold()
    real = [m for m in meetings if "testing" not in m["meeting_name"].casefold()]
    exact = [m for m in real if m["meeting_name"].casefold() == wanted]
    if len(exact) == 1:
        return exact[0]
    partial = [m for m in real if wanted in m["meeting_name"].casefold()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        log.warning("openf1.ambiguous_gp", gp=gp, matches=[m["meeting_name"] for m in partial])
    return None


def find_session(year: int, gp: str, session: str) -> tuple[dict, dict] | None:
    code = CODE_ALIASES.get(session.upper(), session.upper())
    meeting = pick_meeting(of1.fetch_meetings(year, strict=True), gp)
    if meeting is None:
        return None
    for sess in of1.fetch_sessions(meeting["meeting_key"], strict=True):
        if NAME_TO_CODE.get(sess.get("session_name")) == code and not sess.get("is_cancelled"):
            return meeting, sess
    return None


# ── pure transforms (no network, no DB) ───────────────────────────────────────


def build_drivers(rows: list[dict], session_key: int) -> list[dict]:
    out = {}
    for r in rows:
        num = r.get("driver_number")
        if num is None:
            continue
        out[int(num)] = {
            "driver_number": int(num),
            "session_key": session_key,
            "full_name": r.get("full_name") or r.get("broadcast_name") or str(num),
            "abbreviation": r.get("name_acronym") or str(num),
            "team_name": r.get("team_name"),
            "team_colour": r.get("team_colour"),
            "headshot_url": r.get("headshot_url") or None,
        }
    return list(out.values())


def match_deletions(
    rc: list[dict], laps_by_driver: dict[int, list[dict]]
) -> dict[tuple[int, int], str]:
    """Map race-control "TIME ... DELETED" messages to (driver, lap_number).

    Each message deletes at most one lap, and two messages for the same car
    and time delete two different laps. Candidates are the driver's laps with
    the same duration; when several match, the latest one that started before
    the message wins (the message follows the lap it deletes).
    """
    events = []
    for e in rc:
        m = _DELETED_RE.search(e.get("message") or "")
        when = _dt(e.get("date"))
        if m and when:
            events.append((when, int(m["num"]), _lap_time_text_to_ms(m["time"]), m["why"].strip()))
    events.sort(key=lambda t: t[0])

    matched: dict[tuple[int, int], str] = {}
    for when, driver, t_ms, why in events:
        cands = [
            lap
            for lap in sorted(laps_by_driver.get(driver, []), key=lambda r: int(r["lap_number"]))
            if lap.get("lap_duration") is not None
            and abs(_ms(lap["lap_duration"]) - t_ms) < 1.0
            and (driver, int(lap["lap_number"])) not in matched
        ]
        if not cands:
            continue
        before = [lap for lap in cands if (_dt(lap.get("date_start")) or when) <= when]
        pick = before[-1] if before else cands[0]
        matched[(driver, int(pick["lap_number"]))] = why
    return matched


def stint_for_lap(stints: list[dict], lap: int) -> dict | None:
    """The stint a lap belongs to.

    OpenF1 can report degenerate stints, e.g. after a red flag (Monaco 2024:
    stint 1 = laps 1-0, stint 2 = laps 1-78). Skip stints whose end precedes
    their start, and when stints overlap prefer the latest one.
    """
    best = None
    for s in stints:
        start, end = s.get("lap_start"), s.get("lap_end")
        if start is None or start > lap:
            continue
        if end is not None and (end < start or end < lap):
            continue
        if best is None or (s.get("stint_number") or 0) > (best.get("stint_number") or 0):
            best = s
    return best


def derive_incident_periods(rc: list[dict], session_end: datetime | None) -> list[dict]:
    """Safety car / VSC / red flag periods from race-control messages.

    Returns [{code, label, start, end}] with datetimes (end None if never closed).
    Closing events: SC "IN THIS LAP" or a green track flag; VSC "ENDING";
    red flag -> next green track flag / "PIT EXIT OPEN". Periods never overlap:
    a new incident closes whichever one is still open.
    """
    events = sorted(
        ((_dt(e.get("date")), e) for e in rc if _dt(e.get("date"))), key=lambda t: t[0]
    )
    periods: list[dict] = []
    open_p: dict | None = None

    def close(at: datetime, lap: int | None = None) -> None:
        nonlocal open_p
        if open_p is not None:
            open_p["end"], open_p["end_lap"] = at, lap
            periods.append(open_p)
            open_p = None

    def open_(code: str, label: str, at: datetime, lap: int | None) -> None:
        nonlocal open_p
        close(at, lap)
        open_p = {"code": code, "label": label, "start": at, "end": None,
                  "start_lap": lap, "end_lap": None}

    for at, e in events:
        msg = (e.get("message") or "").upper()
        flag = (e.get("flag") or "").upper()
        scope = (e.get("scope") or "").upper()
        lap = e.get("lap_number")
        # A real "track clear / green" flag, not the pit-lane-exit green light.
        track_green = flag in ("GREEN", "CLEAR") and scope in ("TRACK", "") and "PIT EXIT" not in msg
        restarted = msg == "SESSION STARTED"
        if "VIRTUAL SAFETY CAR DEPLOYED" in msg:
            open_("6", "VirtualSafetyCar", at, lap)
        elif "VIRTUAL SAFETY CAR ENDING" in msg:
            if open_p and open_p["code"] == "6":
                close(at, lap)
        elif msg.startswith("SAFETY CAR DEPLOYED"):
            open_("4", "SafetyCar", at, lap)
        elif "SAFETY CAR IN THIS LAP" in msg:
            if open_p and open_p["code"] == "4":
                close(at, lap)
        elif flag == "RED" and scope in ("TRACK", ""):
            if not (open_p and open_p["code"] == "5"):
                open_("5", "Red", at, lap)
        elif open_p and open_p["code"] == "5" and (restarted or track_green):
            close(at, lap)
        elif open_p and open_p["code"] == "4" and track_green and "SAFETY CAR" not in msg:
            close(at, lap)

    if open_p is not None:
        # Left open by the feed: close at session end if we know it.
        open_p["end"] = session_end
        periods.append(open_p)
    return periods


def build_track_status_rows(
    incidents: list[dict],
    session_start: datetime,
    lap_starts: list[tuple[int, datetime]],
    session_key: int,
) -> list[dict]:
    """Sequential periods: incidents with AllClear filling the gaps.

    The AllClear rows matter: the empirical safety-car rate counts a race only
    if it has track-status rows, so a clean race must still produce rows.
    """
    times = [t for _, t in lap_starts]
    laps = [n for n, _ in lap_starts]

    def lap_at(ts: datetime | None) -> int | None:
        return None if ts is None else _at(times, laps, ts)

    def ms(ts: datetime | None) -> float | None:
        return None if ts is None else (ts - session_start).total_seconds() * 1000.0

    def row(code: str, label: str, start: datetime, end: datetime | None,
            start_lap: int | None = None, end_lap: int | None = None) -> dict:
        return {
            "session_key": session_key,
            "status_code": code,
            "status_label": label,
            "start_ms": ms(start),
            "end_ms": ms(end),
            "start_lap": start_lap if start_lap is not None else lap_at(start),
            "end_lap": end_lap if end_lap is not None else lap_at(end),
        }

    rows: list[dict] = []
    cursor, cursor_lap = session_start, None
    for inc in sorted(incidents, key=lambda p: p["start"]):
        if inc["start"] > cursor:
            rows.append(row("1", "AllClear", cursor, inc["start"], cursor_lap, inc.get("start_lap")))
        rows.append(row(inc["code"], inc["label"], inc["start"], inc["end"],
                        inc.get("start_lap"), inc.get("end_lap")))
        if inc["end"] is None:
            return rows
        cursor, cursor_lap = inc["end"], inc.get("end_lap")
    rows.append(row("1", "AllClear", cursor, None, cursor_lap, None))
    return rows


def build_laps(
    laps: list[dict],
    stints: list[dict],
    pits: list[dict],
    positions: list[dict],
    incidents: list[dict],
    rc: list[dict],
    session_start: datetime,
    code: str,
    session_key: int,
) -> list[dict]:
    """Map OpenF1 laps to ``lap_times`` rows (see module docstring for the
    fields that are derived rather than reported)."""
    by_driver: dict[int, list[dict]] = {}
    for lap in laps:
        if lap.get("driver_number") is None or lap.get("lap_number") is None:
            continue
        by_driver.setdefault(int(lap["driver_number"]), []).append(lap)

    stints_by_driver: dict[int, list[dict]] = {}
    for s in stints:
        stints_by_driver.setdefault(int(s["driver_number"]), []).append(s)

    pit_in_ms: dict[tuple[int, int], float | None] = {}
    for p in pits:
        if p.get("driver_number") is None or p.get("lap_number") is None:
            continue
        d = _dt(p.get("date"))
        pit_in_ms[(int(p["driver_number"]), int(p["lap_number"]))] = (
            (d - session_start).total_seconds() * 1000.0 if d else 0.0
        )

    pos_by_driver: dict[int, tuple[list[datetime], list[int]]] = {}
    for p in sorted(positions, key=lambda r: r["date"]):
        d = _dt(p.get("date"))
        if d is None:
            continue
        times, vals = pos_by_driver.setdefault(int(p["driver_number"]), ([], []))
        times.append(d)
        vals.append(int(p["position"]))

    deleted_laps = match_deletions(rc, by_driver)

    phases = sorted(
        (_dt(e["date"]), int(e["qualifying_phase"]))
        for e in rc
        if e.get("qualifying_phase") is not None and _dt(e.get("date"))
    )
    phase_times = [t for t, _ in phases]
    phase_vals = [v for _, v in phases]

    def track_code(start: datetime, end: datetime) -> str:
        for inc in incidents:
            inc_end = inc["end"] or datetime.max.replace(tzinfo=timezone.utc)
            if inc["start"] < end and inc_end > start:
                return inc["code"]
        return "1"

    rows: list[dict] = []
    for driver, dlaps in by_driver.items():
        dlaps.sort(key=lambda r: int(r["lap_number"]))
        best_ms: float | None = None
        for i, lap in enumerate(dlaps):
            n = int(lap["lap_number"])
            start = _dt(lap.get("date_start"))
            duration_ms = _ms(lap.get("lap_duration"))
            nxt = _dt(dlaps[i + 1].get("date_start")) if i + 1 < len(dlaps) else None
            end = nxt or (
                start + timedelta(milliseconds=duration_ms)
                if start and duration_ms
                else start
            )

            stint = stint_for_lap(stints_by_driver.get(driver, []), n)
            age0 = (stint or {}).get("tyre_age_at_start")
            tyre_life = (
                int(age0) + (n - int(stint["lap_start"])) + 1
                if stint and age0 is not None
                else None
            )

            in_pit = (driver, n) in pit_in_ms
            out_pit = bool(lap.get("is_pit_out_lap"))
            pit_out_marker = None
            if (driver, n - 1) in pit_in_ms:
                pit_out_marker = pit_in_ms[(driver, n - 1)]
            elif out_pit and start:
                pit_out_marker = (start - session_start).total_seconds() * 1000.0

            status = track_code(start, end) if start and end else "1"
            sectors = [
                _ms(lap.get(f"duration_sector_{k}")) for k in (1, 2, 3)
            ]
            clean = (
                duration_ms is not None
                and all(x is not None for x in sectors)
                and not in_pit
                and pit_out_marker is None
                and n > 1
                and status == "1"
            )
            del_reason = deleted_laps.get((driver, n))
            is_pb = False
            if duration_ms is not None and del_reason is None and not in_pit and pit_out_marker is None:
                if best_ms is None or duration_ms < best_ms:
                    best_ms, is_pb = duration_ms, True

            position = None
            if code in RACE_LIKE and driver in pos_by_driver and (nxt or end):
                times, vals = pos_by_driver[driver]
                position = _at(times, vals, nxt or end)

            segment = None
            if code in QUALI_LIKE and start and phase_times:
                segment = _at(phase_times, phase_vals, start)

            rows.append(
                {
                    "session_key": session_key,
                    "driver_number": driver,
                    "lap_number": n,
                    "lap_time_ms": duration_ms,
                    "s1_ms": sectors[0],
                    "s2_ms": sectors[1],
                    "s3_ms": sectors[2],
                    "compound": (stint or {}).get("compound"),
                    "tyre_life_laps": tyre_life,
                    "is_personal_best": is_pb,
                    "pit_in_time_ms": pit_in_ms.get((driver, n)),
                    "pit_out_time_ms": pit_out_marker,
                    "track_status": status,
                    "stint": (stint or {}).get("stint_number"),
                    "position": position,
                    "fresh_tyre": (age0 == 0) if age0 is not None else None,
                    "deleted": del_reason is not None,
                    "deleted_reason": del_reason,
                    "is_accurate": clean and del_reason is None,
                    "quali_segment": segment,
                    "speed_i1": lap.get("i1_speed"),
                    "speed_i2": lap.get("i2_speed"),
                    "speed_fl": None,  # OpenF1 has no finish-line speed
                    "speed_st": lap.get("st_speed"),
                }
            )
    return rows


def _status_text(r: dict, leader_laps: int | None) -> tuple[str, str | None]:
    """(status, classified_position) in the vocabulary the DNF queries expect."""
    if r.get("dsq"):
        return "Disqualified", "D"
    if r.get("dns"):
        return "Did not start", "W"
    if r.get("dnf"):
        return "Retired", "R"
    laps, pos = r.get("number_of_laps"), r.get("position")
    behind = (leader_laps - laps) if leader_laps and laps else 0
    status = "Finished" if behind <= 0 else f"+{behind} Lap" + ("s" if behind > 1 else "")
    return status, str(pos) if pos is not None else None


def _race_time_ms(r: dict, code: str) -> float | None:
    """Same meaning as FastF1's results ``Time``: total time for the winner,
    gap to the winner for everyone else (None for lapped / unclassified cars,
    whose OpenF1 gap is text like "+1 LAP")."""
    if code not in RACE_LIKE or isinstance(r.get("duration"), list):
        return None
    if r.get("position") == 1:
        return _ms(r.get("duration"))
    gap = r.get("gap_to_leader")
    return _ms(gap) if isinstance(gap, (int, float)) else None


def build_session_results(
    results: list[dict], drivers: list[dict], grid: list[dict], code: str, session_key: int
) -> list[dict]:
    by_num = {d["driver_number"]: d for d in drivers}
    grid_by = {int(g["driver_number"]): g.get("position") for g in grid if g.get("driver_number")}
    leader_laps = max((r.get("number_of_laps") or 0 for r in results), default=None) if code in RACE_LIKE else None
    rows = []
    for r in results:
        if r.get("driver_number") is None:
            continue
        num = int(r["driver_number"])
        status, classified = _status_text(r, leader_laps)
        duration = r.get("duration")
        q = duration if isinstance(duration, list) else [None, None, None]
        q = (list(q) + [None, None, None])[:3]
        rows.append(
            {
                "session_key": session_key,
                "driver_number": num,
                "abbreviation": by_num.get(num, {}).get("abbreviation"),
                "team_name": by_num.get(num, {}).get("team_name"),
                "grid_position": grid_by.get(num),
                "position": r.get("position"),
                "classified_position": classified,
                "status": status,
                "points": r.get("points"),
                "laps_completed": r.get("number_of_laps"),
                "race_time_ms": _race_time_ms(r, code),
                "q1_ms": _ms(q[0]) if code in QUALI_LIKE else None,
                "q2_ms": _ms(q[1]) if code in QUALI_LIKE else None,
                "q3_ms": _ms(q[2]) if code in QUALI_LIKE else None,
            }
        )
    return rows


def build_race_control(rc: list[dict], session_key: int) -> list[dict]:
    return [
        {
            "session_key": session_key,
            "category": e.get("category"),
            "flag": e.get("flag"),
            "scope": e.get("scope"),
            "driver_number": e.get("driver_number"),
            "sector": e.get("sector"),
            "lap_number": e.get("lap_number"),
            "message": e.get("message"),
        }
        for e in rc
    ]


def build_weather_events(
    weather: list[dict], lap_starts: list[tuple[int, datetime]], session_key: int
) -> list[dict]:
    times = [t for _, t in lap_starts]
    laps = [n for n, _ in lap_starts]
    rows = []
    for w in weather:
        d = _dt(w.get("date"))
        if d is None:
            continue
        rows.append(
            {
                "session_key": session_key,
                "timestamp": d.isoformat(),
                "lap_number": _at(times, laps, d),
                "track_temp_c": w.get("track_temperature"),
                "air_temp_c": w.get("air_temperature"),
                "humidity_pct": w.get("humidity"),
                "rainfall": bool(w.get("rainfall")),
                "wind_speed_ms": w.get("wind_speed"),
            }
        )
    return rows


def earliest_lap_starts(laps: list[dict]) -> list[tuple[int, datetime]]:
    """(lap_number, earliest start across drivers), sorted by time."""
    best: dict[int, datetime] = {}
    for lap in laps:
        d, n = _dt(lap.get("date_start")), lap.get("lap_number")
        if d is None or n is None:
            continue
        if int(n) not in best or d < best[int(n)]:
            best[int(n)] = d
    return sorted(best.items(), key=lambda kv: kv[1])


def annotate_laps(rows: list[dict], laps: list[dict]) -> None:
    """Add lap_number to timestamped rows using each driver's own lap starts."""
    per_driver: dict[int, tuple[list[datetime], list[int]]] = {}
    for lap in sorted(laps, key=lambda r: (r.get("driver_number") or 0, r.get("lap_number") or 0)):
        d = _dt(lap.get("date_start"))
        if d is None or lap.get("driver_number") is None:
            continue
        times, nums = per_driver.setdefault(int(lap["driver_number"]), ([], []))
        times.append(d)
        nums.append(int(lap["lap_number"]))
    for r in rows:
        d = _dt(r.get("date"))
        times_nums = per_driver.get(int(r["driver_number"]))
        r["lap_number"] = _at(*times_nums, d) if times_nums and d else None


# ── orchestration ─────────────────────────────────────────────────────────────


_SESSION_TABLES = (
    "lap_times",
    "drivers",
    "race_control_events",
    "weather_events",
    "team_radio",
    "track_status_periods",
    "session_results",
    "session_intervals",
    "position_changes",
    "pit_stops",
)


def _session_has_laps(session_key: int) -> bool:
    with _get_engine().connect() as conn:
        return bool(
            conn.execute(
                text("SELECT 1 FROM lap_times WHERE session_key = :sk LIMIT 1"),
                {"sk": session_key},
            ).first()
        )


def _session_exists(session_key: int) -> bool:
    with _get_engine().connect() as conn:
        return bool(
            conn.execute(
                text("SELECT 1 FROM sessions WHERE session_key = :sk"), {"sk": session_key}
            ).first()
        )


def _purge_session(session_key: int) -> None:
    """Remove a session and everything loaded for it (FK order: children first).

    Table names come from the fixed ``_SESSION_TABLES`` tuple, never input.
    """
    with _get_engine().begin() as conn:
        for table in _SESSION_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE session_key = :sk"), {"sk": session_key})
        conn.execute(text("DELETE FROM sessions WHERE session_key = :sk"), {"sk": session_key})


def ingest_openf1_session(
    meeting: dict, sess: dict, *, force: bool = False
) -> int | None:
    """Ingest one session from OpenF1. Returns the session_key, or None when the
    session is not ready (no laps yet / still running) or is skipped.

    Every required dataset is fetched (strictly: an outage raises
    ``OpenF1Error`` rather than looking like "no data") before anything is
    written. If a write then fails for a session this call created, the
    half-written session is removed again, so ``auto_ingest`` (which trusts the
    ``sessions`` table) retries it instead of treating it as done.
    """
    info = build_session_info(meeting, sess)
    start = _dt(sess.get("date_start"))
    if info is None or start is None:
        return None
    key, code = info["session_key"], info["session_type"]

    if not force and _session_has_laps(key):
        log.info("openf1.skip_existing", session_key=key, gp=info["gp_name"], session=code)
        return None
    end = _dt(sess.get("date_end"))
    if end and end > datetime.now(timezone.utc):
        log.info("openf1.not_finished", session_key=key)
        return None

    # ---- fetch phase (no writes) ----
    raw_laps = of1.fetch_laps(key, strict=True)
    if not raw_laps:
        log.info("openf1.no_laps", session_key=key)
        return None
    drivers = build_drivers(of1.fetch_drivers(key, strict=True), key)
    stints = of1.fetch_stints(key, strict=True)
    rc = of1.fetch_race_control(key, strict=True)
    weather_raw = of1.fetch_weather(key, strict=True)
    results_raw = of1.fetch_session_result(key, strict=True)
    pits = of1.fetch_pit_stops(key, strict=True)
    positions = of1.fetch_positions(key, strict=True) if code in RACE_LIKE else []
    intervals = of1.fetch_intervals(key, strict=True) if code in RACE_LIKE else []
    grid = of1.fetch_starting_grid(key)  # best effort: not published for every session
    radio = of1.fetch_team_radio(key)  # best effort

    # ---- build phase (pure) ----
    incidents = derive_incident_periods(rc, end)
    laps = build_laps(raw_laps, stints, pits, positions, incidents, rc, start, code, key)
    lap_starts = earliest_lap_starts(raw_laps)
    wx_rows = build_weather_events(weather_raw, lap_starts, key)
    track_rows = build_track_status_rows(incidents, start, lap_starts, key)
    result_rows = build_session_results(results_raw, drivers, grid, code, key)
    annotate_laps(radio, raw_laps)
    annotate_laps(intervals, raw_laps)
    pos_rows = [dict(p) for p in positions]
    annotate_laps(pos_rows, raw_laps)

    # ---- write phase ----
    created = not _session_exists(key)
    timing = {"intervals": 0, "positions": 0, "pit_stops": 0}
    try:
        upsert_session(info)
        load_drivers(drivers)
        lap_count = load_laps(laps, key)
        load_weather_events(wx_rows, key)
        if weather_raw:
            last = weather_raw[-1]
            update_session_weather(
                key,
                track_temp=last.get("track_temperature"),
                air_temp=last.get("air_temperature"),
                humidity=last.get("humidity"),
                rainfall=bool(last.get("rainfall")),
                wind_speed=last.get("wind_speed"),
            )
        load_race_control(build_race_control(rc, key), key)
        load_track_status(track_rows, key)
        load_session_results(result_rows, key)
        load_team_radio(radio, key)
        if code in RACE_LIKE:
            timing["intervals"] = load_session_intervals(intervals, key)
            timing["positions"] = load_position_changes(pos_rows, key)
            timing["pit_stops"] = load_pit_stops(pits, key)
    except Exception:
        if created:
            try:
                _purge_session(key)
                log.warning("openf1.partial_ingest_removed", session_key=key)
            except Exception as cleanup_exc:  # keep the original error as the cause
                log.error("openf1.cleanup_failed", session_key=key, error=str(cleanup_exc))
        raise

    log.info(
        "openf1.ingest_done",
        session_key=key,
        gp=info["gp_name"],
        session=code,
        laps=lap_count,
        drivers=len(drivers),
        **{f"openf1_{k}": v for k, v in timing.items()},
    )
    return key


def ingest_session_openf1(
    year: int, gp: str, session: str, *, force: bool = False
) -> int | None:
    """Look a session up by (year, GP name, code) and ingest it."""
    found = find_session(year, gp, session)
    if found is None:
        log.warning("openf1.session_not_found", year=year, gp=gp, session=session)
        return None
    return ingest_openf1_session(*found, force=force)


def backfill_year(year: int, *, force: bool = False) -> dict[str, int]:
    """Ingest every finished session of ``year`` that is not in the DB yet."""
    counts = {"ingested": 0, "skipped": 0, "failed": 0}
    for meeting in of1.fetch_meetings(year, strict=True):
        if "testing" in meeting["meeting_name"].casefold():
            continue
        for sess in of1.fetch_sessions(meeting["meeting_key"], strict=True):
            if NAME_TO_CODE.get(sess.get("session_name")) is None:
                continue
            try:
                key = ingest_openf1_session(meeting, sess, force=force)
                counts["ingested" if key else "skipped"] += 1
            except Exception as exc:
                counts["failed"] += 1
                log.error("openf1.session_failed", session_key=sess.get("session_key"), error=str(exc))
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest sessions from OpenF1 (no FastF1)")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--gp", type=str, help='GP name, e.g. "Bahrain" or "Monaco Grand Prix"')
    parser.add_argument("--session", type=str, help="R, Q, SS, SQ, FP1, FP2, FP3")
    parser.add_argument("--all", action="store_true", help="every finished session of the year")
    parser.add_argument("--force", action="store_true", help="replace sessions that already have laps")
    args = parser.parse_args(argv)

    try:
        if args.all:
            print(backfill_year(args.year, force=args.force))
            return 0
        if not (args.gp and args.session):
            parser.error("give --gp and --session, or --all")
        key = ingest_session_openf1(args.year, args.gp, args.session, force=args.force)
    except of1.OpenF1Restricted as exc:
        # Not a crash: OpenF1 lifts this restriction when the live session ends.
        print(f"OpenF1 is blocking access right now: {exc}. Retry after the session ends.")
        return 2
    print({"session_key": key})
    return 0 if key else 1


if __name__ == "__main__":
    raise SystemExit(main())
