"""
Read-only agent tools — deterministic functions that query Postgres.

Rules:
- SQL lives here, inside these functions. It never comes from the LLM.
- Each tool takes one typed input dataclass and returns one typed output.
- Tools never write to the database.
"""

from __future__ import annotations
import gzip
import io
import json
from pathlib import Path
import re
import socket

import botocore
from sqlalchemy import text

from backend import extensions
from backend import strategy_documents, vector_store
from backend.config import settings
from backend.agent import strategy, types
import statistics

_MAX_CATALOG_LIMIT = 200
_MAX_SOURCE_LIMIT = 50
_SOURCE_EXCERPT_CHARS = 320


def resolve_session(inp: types.ResolveSessionInput) -> types.ResolvedSession:
    """Find the most recent session matching the given year, GP name, and session type."""
    cleaned_gp = re.sub(
        r"\b(grand prix|gp)\b", "", inp.gp_name, flags=re.IGNORECASE
    ).strip()
    search_term = cleaned_gp if cleaned_gp else inp.gp_name.strip()

    with extensions.engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT session_key, year, gp_name, session_type, session_name 
                    FROM sessions
                    WHERE year = :year 
                      AND (gp_name ILIKE :gp_pattern OR country ILIKE :gp_pattern)
                      AND session_type = :stype
                    ORDER BY date_start DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {
                    "year": inp.year,
                    "gp_pattern": f"%{search_term}%",
                    "stype": inp.session_type.value,
                },
            )
            .mappings()
            .first()
        )
    if row is None:
        raise types.NotFoundError(
            f"No {inp.session_type.value} session found for {inp.gp_name} {inp.year}"
        )

    return types.ResolvedSession(
        session_key=row["session_key"],
        year=row["year"],
        gp_name=row["gp_name"],
        session_type=types.SessionType(row["session_type"]),
        session_name=row["session_name"],
    )


def resolve_driver(inp: types.ResolveDriverInput) -> types.ResolvedDriver:
    """Resolve a driver title by its abbervaition, name, or number to a session specific driver.

    It uses a signle query with three OR conditions to find the driver. If multiple drivers match, it returns the one with the lowest driver number.
    """

    term = inp.name_or_abbreviation.strip()
    if term.isdigit():
        numeric = int(term)
    else:
        numeric = None

    params = {
        "sk": inp.session_key,
        "num": numeric,
        "abbr": term,
        "name": f"%{term}%",
    }

    with extensions.engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT d.driver_number, d.abbreviation, d.full_name, d.team_name
                    FROM drivers d
                    WHERE d.session_key = :sk
                      AND (
                        d.driver_number = :num
                        OR d.abbreviation ILIKE :abbr
                        OR d.full_name ILIKE :name
                      )
                    ORDER BY d.driver_number
                    LIMIT 1
                    """
                ),
                params,
            )
            .mappings()
            .first()
        )

    if row is None:
        raise types.NotFoundError(
            f"Driver '{inp.name_or_abbreviation}' not found in session {inp.session_key}"
        )

    return types.ResolvedDriver(
        driver_number=row["driver_number"],
        abbreviation=row["abbreviation"],
        full_name=row["full_name"],
        team_name=row["team_name"],
    )


def _derive_pit_stops(laps: list[dict]) -> list[types.PitStop]:
    """
    Derive pit stops from a list of lap dictionaries.
    """
    stops: list[types.PitStop] = []
    for i, lap in enumerate(laps):
        if lap["pit_in_time_ms"] is None:
            continue

        pit_in_lap = lap["lap_number"]

        pit_out_lap = None
        for following in laps[i + 1 :]:
            if following["pit_out_time_ms"] is not None:
                pit_out_lap = following["lap_number"]
                break
        if pit_out_lap is None:
            pit_out_lap = pit_in_lap + 1

        compound_before = next(
            (p["compound"] for p in reversed(laps[:i]) if p["compound"]), None
        )
        compound_after = next(
            (p["compound"] for p in laps[i + 1 :] if p["compound"]), None
        )

        stops.append(
            types.PitStop(
                stop_index=len(stops) + 1,
                pit_in_lap=pit_in_lap,
                pit_out_lap=pit_out_lap,
                compound_before=compound_before,
                compound_after=compound_after,
            )
        )
    return stops


def _cumulative_race_times(laps: list[dict], up_to_lap: int) -> dict[int, int]:
    """Commulative race time per driver through 'up_to_lap'

    Input: raw lap rows {driver_number, lap_number, lap_time_ms}
    Output: {driver_number: ms}.
    A "cumulative time" is just the sum of a driver's completed lap times so far — lower = ahead on track.
    """

    by_driver: dict[list, list[dict]] = {}
    for lap in laps:
        if lap.get("lap_time_ms") is None:
            continue
        by_driver.setdefault(lap["driver_number"], []).append(lap)

    commulative: dict[int, int] = {}
    for dn, driver_laps in by_driver.items():
        total = 0
        for lap in sorted(driver_laps, key=lambda ln: ln["lap_number"]):
            if lap["lap_number"] > up_to_lap:
                break
            total += int(lap["lap_time_ms"])
        commulative[dn] = total
    return commulative


def _gap_snapshot(
    commulative: dict[int, int],
    driver_number: int,
    target_lap: int,
    stored_position: int | None,
) -> types.GapPositionSnapshot:
    """Turn commulative times into a gapped snapshot at one lap.

    rank = sort ascending by commulative time (smallest = first = leader)
    'car ahead': the driver who's time is just smaller than ours
    'car behind': the driver who's time is just bigger than ours
    """

    if driver_number not in commulative:
        raise types.NotFoundError(
            f"Driver {driver_number} has not completed upto lap {target_lap}"
        )

    ordered = sorted(commulative.items(), key=lambda kv: kv[1])
    idx = ordered.index((driver_number, commulative[driver_number]))
    rank = {dn: i + 1 for i, (dn, _) in enumerate(ordered)}
    own = commulative[driver_number]
    leader_number, leader_ms = ordered[0]
    ahead_number, ahead_ms = ordered[idx - 1] if idx > 0 else (None, None)
    behind_number, behind_ms = (
        ordered[idx + 1] if idx < len(ordered) - 1 else (None, None)
    )

    return types.GapPositionSnapshot(
        lap_number=target_lap,
        position=stored_position
        if stored_position is not None
        else rank[driver_number],
        cumulative_ms=int(own),
        leader_number=leader_number,
        leader_cumulative_ms=int(leader_ms),
        gap_to_leader_ms=int(own - leader_ms),
        car_ahead_number=ahead_number,
        car_ahead_gap_ms=int(own - ahead_ms) if ahead_ms is not None else None,
        car_behind_number=behind_number,
        car_behind_gap_ms=int(behind_ms - own) if behind_ms is not None else None,
    )


def find_pit_stops(inp: types.FindPitStopsInput) -> types.PitStopsResult:
    """Detect pit stops for one driver in one session."""
    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
                    SELECT lap_number, pit_in_time_ms, pit_out_time_ms, compound
                    FROM lap_times
                    WHERE session_key = :sk
                      AND driver_number = :dn
                      AND deleted = FALSE
                    ORDER BY lap_number ASC
                """),
                {"sk": inp.session_key, "dn": inp.driver_number},
            )
            .mappings()
            .all()
        )

    stops = _derive_pit_stops([dict(r) for r in rows])
    return types.PitStopsResult(driver_number=inp.driver_number, pit_stops=tuple(stops))


def gap_and_position_snapshot(inp: types.GapPositionInput) -> types.GapPositionSnapshot:
    """Snapshot the field at one lap: the driver's position, gap to the leader, and gaps to the car directly ahead and behind"""
    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
                    SELECT driver_number, lap_number, lap_time_ms, position
                    FROM lap_times
                    WHERE session_key = :sk
                      AND deleted = FALSE
                      AND lap_time_ms IS NOT NULL
                    ORDER BY driver_number ASC, lap_number ASC
                """),
                {"sk": inp.session_key},
            )
            .mappings()
            .all()
        )

    if not rows:
        raise types.NotFoundError(f"No lap data found for session {inp.session_key}")

    target_lap = inp.target_lap
    if target_lap is None:
        driver_laps = [r for r in rows if r["driver_number"] == inp.driver_number]
        if not driver_laps:
            raise types.NotFoundError(
                f"Driver {inp.driver_number} has no laps in session {inp.session_key}"
            )
        target_lap = max(r["lap_number"] for r in driver_laps)

    cumulative = _cumulative_race_times([dict(r) for r in rows], target_lap)

    stored_position = next(
        (
            r["position"]
            for r in rows
            if r["driver_number"] == inp.driver_number and r["lap_number"] == target_lap
        ),
        None,
    )

    return _gap_snapshot(cumulative, inp.driver_number, target_lap, stored_position)


def _count_sc_periods(rows: list[dict]) -> int:
    """Count distinct contiguous period ranges that are under SC or VSC"""
    sc_laps = sorted(
        {
            r["lap_number"]
            for r in rows
            if r["flag"] in ("SC", "VSC", "SAFETY CAR", "VIRTUAL SAFETY CAR", "RED")
            and r["lap_number"] is not None
        }
    )
    if not sc_laps:
        return 0
    periods = 1
    for i in range(1, len(sc_laps)):
        if sc_laps[i] != sc_laps[i - 1] + 1:
            periods += 1
    return periods


def fetch_race_control_window(
    inp: types.RaceControlWindowInput,
) -> types.RaceControlWindowResult:
    """All flag/SC/VSC events intersecting a lap window for a session."""
    with extensions.engine.connect() as conn:
        sql = """
            SELECT category, flag, scope, driver_number, sector,
                   lap_number, message
            FROM race_control_events
            WHERE session_key = :sk
        """
        binds: dict = {"sk": inp.session_key}
        if inp.driver_number is not None:
            sql += " AND (driver_number = :dn OR scope = 'Track')"
            binds["dn"] = inp.driver_number
        if inp.from_lap is not None:
            sql += " AND lap_number >= :fl"
            binds["fl"] = inp.from_lap
        if inp.to_lap is not None:
            sql += " AND lap_number <= :tl"
            binds["tl"] = inp.to_lap
        sql += " ORDER BY lap_number ASC, id ASC"
        rows = conn.execute(text(sql), binds).mappings().all()

    events = tuple(
        types.RaceControlEvent(
            category=r["category"],
            flag=r["flag"],
            scope=r["scope"],
            driver_number=r["driver_number"],
            sector=r["sector"],
            lap_number=r["lap_number"],
            message=r["message"],
        )
        for r in rows
    )

    sc_periods = _count_sc_periods(rows)
    return types.RaceControlWindowResult(
        from_lap=inp.from_lap,
        to_lap=inp.to_lap,
        events=events,
        safety_car_periods=sc_periods,
    )


def fetch_track_status(inp: types.TrackStatusInput) -> types.TrackStatusResult:
    """Safety car / VSC / red flag / yellow periods from the timing feed.

    Unlike race-control messages (text events), these are closed periods with
    start/end, so "how long was the safety car out" is a subtraction.
    """
    if inp.from_lap is not None and inp.to_lap is not None and inp.from_lap > inp.to_lap:
        # An inverted window contains no laps; don't let spanning periods match.
        return types.TrackStatusResult(
            from_lap=inp.from_lap, to_lap=inp.to_lap, periods=()
        )
    with extensions.engine.connect() as conn:
        # start_lap / end_lap are NULL for times before lap 1 starts, so NULL
        # means "lap 0" rather than "unknown". The final period is open-ended:
        # it is marked by end_ms IS NULL (its end_lap is NULL too).
        sql = """
            SELECT status_code, status_label, start_ms, end_ms, start_lap, end_lap
            FROM track_status_periods
            WHERE session_key = :sk
        """
        binds: dict = {"sk": inp.session_key}
        if inp.to_lap is not None:
            sql += " AND COALESCE(start_lap, 0) <= :tl"
            binds["tl"] = inp.to_lap
        if inp.from_lap is not None:
            sql += " AND (end_ms IS NULL OR COALESCE(end_lap, 0) >= :fl)"
            binds["fl"] = inp.from_lap
        sql += " ORDER BY start_ms ASC, id ASC"
        rows = conn.execute(text(sql), binds).mappings().all()
        has_yellow_data = bool(
            conn.execute(
                text(
                    "SELECT 1 FROM track_status_periods "
                    "WHERE session_key = :sk AND status_code = '2' LIMIT 1"
                ),
                {"sk": inp.session_key},
            ).first()
        )

    periods = tuple(
        types.TrackStatusPeriod(
            status_code=r["status_code"],
            status_label=r["status_label"],
            start_ms=r["start_ms"],
            end_ms=r["end_ms"],
            start_lap=r["start_lap"],
            end_lap=r["end_lap"],
        )
        for r in rows
    )

    def count(code: str) -> int:
        return sum(1 for p in periods if p.status_code == code)

    return types.TrackStatusResult(
        from_lap=inp.from_lap,
        to_lap=inp.to_lap,
        periods=periods,
        safety_car_periods=count("4"),
        vsc_periods=count("6"),
        red_flag_periods=count("5"),
        # Sessions with no yellow row at all were not tracked for yellows.
        yellow_periods=count("2") if has_yellow_data else None,
    )


def fetch_session_results(
    inp: types.SessionResultsInput,
) -> types.SessionResultsResult:
    """Official classification: grid, finish, status, points, Q1/Q2/Q3."""
    with extensions.engine.connect() as conn:
        sql = """
            SELECT driver_number, abbreviation, team_name, grid_position,
                   position, classified_position, status, points,
                   laps_completed, race_time_ms, q1_ms, q2_ms, q3_ms
            FROM session_results
            WHERE session_key = :sk
        """
        binds: dict = {"sk": inp.session_key}
        if inp.driver_number is not None:
            sql += " AND driver_number = :dn"
            binds["dn"] = inp.driver_number
        sql += " ORDER BY position ASC NULLS LAST, driver_number ASC"
        rows = conn.execute(text(sql), binds).mappings().all()

    entries = tuple(
        types.SessionResultEntry(
            **dict(r),
            positions_gained=(
                r["grid_position"] - r["position"]
                if r["grid_position"] and r["position"]
                else None
            ),
        )
        for r in rows
    )
    return types.SessionResultsResult(entries=entries)


def _radio_lap_counts(messages: tuple[types.RadioMessage, ...]) -> int:
    return len(messages)


def fetch_radio_messages(inp: types.RadioWindowInput) -> types.RadioWindowResult:
    """All team radio clips intersecting a lap window for a driver."""
    with extensions.engine.connect() as conn:
        sql = """
            SELECT date, recording_url, transcript
            FROM team_radio
            WHERE session_key = :sk
              AND driver_number = :dn
        """
        binds: dict = {"sk": inp.session_key, "dn": inp.driver_number}
        if inp.from_lap is not None:
            sql += " AND lap_number >= :fl"
            binds["fl"] = inp.from_lap
        if inp.to_lap is not None:
            sql += " AND lap_number <= :tl"
            binds["tl"] = inp.to_lap
        sql += " ORDER BY date ASC NULLS LAST, id ASC"
        rows = conn.execute(text(sql), binds).mappings().all()

    messages = tuple(
        types.RadioMessage(
            date=r["date"],
            recording_url=r["recording_url"],
            transcript=r["transcript"],
        )
        for r in rows
    )
    return types.RadioWindowResult(
        driver_number=inp.driver_number,
        from_lap=inp.from_lap,
        to_lap=inp.to_lap,
        messages=messages,
        clip_count=_radio_lap_counts(messages),
    )


def _rain_stats(samples: list[types.WeatherEventSample]) -> dict:
    """Derive rain + track-temp stats from a list of weather samples."""
    distinct_laps = sorted({s.lap_number for s in samples if s.lap_number is not None})
    rainfall_laps = sorted(
        {s.lap_number for s in samples if s.rainfall and s.lap_number is not None}
    )
    track_temps = [s.track_temp_c for s in samples if s.track_temp_c is not None]
    track_temp_delta = None
    if track_temps:
        track_temp_delta = round(max(track_temps) - min(track_temps), 2)
    return {
        "rainfall_laps": len(rainfall_laps),
        "total_laps": len(distinct_laps),
        "rain_share_pct": round(len(rainfall_laps) / len(distinct_laps) * 100, 2)
        if distinct_laps
        else 0.0,
        "track_temp_delta_c": track_temp_delta,
    }


def fetch_weather_window(inp: types.WeatherWindowInput) -> types.WeatherWindowResult:
    """All weather events intersecting a lap window for a session."""
    with extensions.engine.connect() as conn:
        sql = """
            SELECT timestamp, lap_number, track_temp_c, air_temp_c,
                   humidity_pct, rainfall, wind_speed_ms
            FROM weather_events
            WHERE session_key = :sk
        """
        binds: dict = {"sk": inp.session_key}
        if inp.from_lap is not None:
            sql += " AND lap_number >= :fl"
            binds["fl"] = inp.from_lap
        if inp.to_lap is not None:
            sql += " AND lap_number <= :tl"
            binds["tl"] = inp.to_lap
        sql += " ORDER BY timestamp ASC NULLS LAST"
        rows = conn.execute(text(sql), binds).mappings().all()

    samples = tuple(
        types.WeatherEventSample(
            timestamp=r["timestamp"],
            lap_number=r["lap_number"],
            track_temp_c=r["track_temp_c"],
            air_temp_c=r["air_temp_c"],
            humidity_pct=r["humidity_pct"],
            rainfall=bool(r["rainfall"]),
            wind_speed_ms=r["wind_speed_ms"],
        )
        for r in rows
    )
    stats = _rain_stats(list(samples))
    return types.WeatherWindowResult(
        from_lap=inp.from_lap,
        to_lap=inp.to_lap,
        samples=samples,
        **stats,
    )


def get_lap_telemetry_artifacts(
    inp: types.GetLapTelemetryArtifactsInput,
) -> types.LapTelemetryResult:
    """
    Return artifact metadata (not raw samples) for the requested laps.
    This proves telemetry exists before we compute speed from it.
    """
    if not inp.lap_numbers:
        raise types.DataError("lap_numbers is required to load telemetry artifacts")

    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text("""
                    SELECT
                        session_key, driver_number, lap_number,
                        storage_key, storage_backend, format,
                        sample_count, size_bytes, checksum_sha256
                    FROM telemetry_artifacts
                    WHERE session_key = :sk
                      AND driver_number = :dn
                      AND lap_number = ANY(:laps)
                    ORDER BY lap_number ASC
                """),
                {
                    "sk": inp.session_key,
                    "dn": inp.driver_number,
                    "laps": list(inp.lap_numbers),
                },
            )
            .mappings()
            .all()
        )

    artifacts = tuple(types.TelemetryArtifact(**dict(r)) for r in rows)
    return types.LapTelemetryResult(
        session_key=inp.session_key,
        driver_number=inp.driver_number,
        artifacts=artifacts,
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    """Weighted average: sum(v*w) / sum(w). Returns 0.0 if weights sum to zero."""
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_weight


def _read_artifact_speed_samples(artifact: types.TelemetryArtifact) -> list[float]:
    """Read speed kmph values from a telemtry artifact (local file or S3) and return them as a list of floats."""

    if artifact.storage_backend == "local" and artifact.format == "json.gz":
        path = Path(settings.telemetry_artifact_dir) / artifact.storage_key
        if not path.exists():
            raise types.DataError(f"artifact file not found : {path}")
        with gzip.open(path, "rb") as f:
            payload = json.loads(f.read().decode("utf-8"))
        speeds = [
            float(s["speed_kmh"])
            for s in payload.get("samples", [])
            if s.get("speed_kmh") is not None
        ]

    elif artifact.storage_backend == "local" and artifact.format == "parquet":
        import pyarrow.parquet as pq

        path = Path(settings.telemetry_artifact_dir) / artifact.storage_key
        if not path.exists():
            raise types.DataError(f"artifact file not found : {path}")
        table = pq.read_parquet(path)
        speeds = [
            float(v) for v in table.column("speed_kmh").to_pylist() if v is not None
        ]

    elif artifact.storage_backend == "r2" and artifact.format == "parquet":
        import boto3
        import pyarrow.parquet as pq

        client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
        try:
            obj = client.get_object(
                Bucket=settings.telemetry_artifact_bucket,
                Key=artifact.storage_key,
            )
        except client.exceptions.NoSuchKey as exc:
            raise types.DataError(
                f"artifact missing in R2: {artifact.storage_key}"
            ) from exc
        except (botocore.exceptions.BotoCoreError, TimeoutError, socket.timeout) as exc:
            raise types.RetryableError(f"R2 fetch failed (transient): {exc}") from exc
        table = pq.read_table(io.BytesIO(obj["Body"].read()))
        speeds = [
            float(v) for v in table.column("speed_kmh").to_pylist() if v is not None
        ]

    else:
        raise types.DataError(
            f"unsupported artifact: {artifact.storage_backend}/{artifact.format}"
        )

    return speeds


def _read_artifact_speed_and_distance(
    artifact: types.TelemetryArtifact,
) -> tuple[list[float], list[float]]:
    """Read speed and distance samples from a telemetry artifact.

    Returns (speeds, distances) where distances[i] is the distance in meters
    covered between speed sample i and the next sample. The last sample's
    distance defaults to 0.0 (no next sample to compute interval distance).
    """
    if artifact.storage_backend == "local" and artifact.format == "json.gz":
        path = Path(settings.telemetry_artifact_dir) / artifact.storage_key
        if not path.exists():
            raise types.DataError(f"artifact file not found : {path}")
        with gzip.open(path, "rb") as f:
            payload = json.loads(f.read().decode("utf-8"))
        raw = payload.get("samples", [])
        speeds = [float(s["speed_kmh"]) for s in raw if s.get("speed_kmh") is not None]
        distances = [
            float(s.get("distance_m", 0.0))
            for s in raw
            if s.get("speed_kmh") is not None
        ]

    elif artifact.storage_backend == "local" and artifact.format == "parquet":
        import pyarrow.parquet as pq

        path = Path(settings.telemetry_artifact_dir) / artifact.storage_key
        if not path.exists():
            raise types.DataError(f"artifact file not found : {path}")
        table = pq.read_parquet(path)
        speed_col = table.column("speed_kmh").to_pylist()
        dist_col = (
            table.column("distance_m").to_pylist()
            if "distance_m" in table.column_names
            else [0.0] * len(speed_col)
        )
        speeds = [float(v) for v in speed_col if v is not None]
        distances = [
            float(d) if d is not None else 0.0
            for v, d in zip(speed_col, dist_col)
            if v is not None
        ]

    elif artifact.storage_backend == "r2" and artifact.format == "parquet":
        import boto3
        import pyarrow.parquet as pq

        client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
        try:
            obj = client.get_object(
                Bucket=settings.telemetry_artifact_bucket,
                Key=artifact.storage_key,
            )
        except client.exceptions.NoSuchKey as exc:
            raise types.DataError(
                f"artifact missing in R2: {artifact.storage_key}"
            ) from exc
        except (botocore.exceptions.BotoCoreError, TimeoutError, socket.timeout) as exc:
            raise types.RetryableError(f"R2 fetch failed (transient): {exc}") from exc
        table = pq.read_table(io.BytesIO(obj["Body"].read()))
        speed_col = table.column("speed_kmh").to_pylist()
        dist_col = (
            table.column("distance_m").to_pylist()
            if "distance_m" in table.column_names
            else [0.0] * len(speed_col)
        )
        speeds = [float(v) for v in speed_col if v is not None]
        distances = [
            float(d) if d is not None else 0.0
            for v, d in zip(speed_col, dist_col)
            if v is not None
        ]

    else:
        raise types.DataError(
            f"unsupported artifact: {artifact.storage_backend}/{artifact.format}"
        )

    return speeds, distances


def compute_speed_window(inp: types.ComputeSpeedWindowInput) -> types.SpeedWindowResult:
    """
    Average telemetry speed before and after a given lap window for a driver in a session.

    Supports two metrics:
    - TELEMETRY_SAMPLE_MEAN: plain average of all speed samples (simple but slightly biased
      by sampling rate — fast laps get more samples).
    - DISTANCE_WEIGHTED_TELEMETRY: each sample weighted by the distance it covers,
      giving the true average speed over distance traveled (more accurate).
    """
    if inp.metric not in (
        types.SpeedMetric.TELEMETRY_SAMPLE_MEAN,
        types.SpeedMetric.DISTANCE_WEIGHTED_TELEMETRY,
    ):
        raise types.DataError(f"unsupported metric: {inp.metric}")
    if not inp.before_laps and not inp.after_laps:
        raise types.DataError("before_laps and after_laps cannot both be empty")

    laps_needed = tuple(sorted(set(inp.before_laps) | set(inp.after_laps)))
    artifacts = get_lap_telemetry_artifacts(
        types.GetLapTelemetryArtifactsInput(
            session_key=inp.session_key,
            driver_number=inp.driver_number,
            lap_numbers=laps_needed,
        )
    ).artifacts
    by_lap = {a.lap_number: a for a in artifacts}

    def _window_mean(lap_window: tuple[int, ...]) -> tuple[float, int]:
        missing = [ln for ln in lap_window if ln not in by_lap]
        if missing:
            raise types.DataError(f"no telemetry artifact for laps {missing}")

        if inp.metric is types.SpeedMetric.DISTANCE_WEIGHTED_TELEMETRY:
            all_speeds: list[float] = []
            all_distances: list[float] = []
            for lap in lap_window:
                speeds, distances = _read_artifact_speed_and_distance(by_lap[lap])
                all_speeds.extend(speeds)
                all_distances.extend(distances)
            if not all_speeds:
                raise types.DataError("telemetry artifacts contain zero speed samples")
            avg = _weighted_mean(all_speeds, all_distances)
            return avg, len(all_speeds)
        else:
            flat = [
                v
                for lap in lap_window
                for v in _read_artifact_speed_samples(by_lap[lap])
            ]
            if not flat:
                raise types.DataError("telemetry artifacts contain zero speed samples")
            return _mean(flat), len(flat)

    before_avg, before_count = (
        _window_mean(tuple(inp.before_laps)) if inp.before_laps else (None, 0)
    )
    after_avg, after_count = (
        _window_mean(tuple(inp.after_laps)) if inp.after_laps else (None, 0)
    )

    delta = None
    if before_avg is not None and after_avg is not None:
        delta = round(after_avg - before_avg, 2)

    return types.SpeedWindowResult(
        session_key=inp.session_key,
        driver_number=inp.driver_number,
        metric=inp.metric,
        before_laps=inp.before_laps,
        after_laps=inp.after_laps,
        before_avg_speed_kmh=round(before_avg, 2) if before_avg is not None else None,
        after_avg_speed_kmh=round(after_avg, 2) if after_avg is not None else None,
        delta_kmh=delta,
        sample_count_before=before_count,
        sample_count_after=after_count,
    )


def _detect_lap_anomalies(
    events: list[types.LapEvent], median_ms: int
) -> list[types.LapEvent]:
    """Flag laps more than 3s off the median pace and explain WHY.

    Returns NEW LapEvent objects: the input is never mutated, so this stays
    a pure, unit-testable function.
    """
    if median_ms <= 0:
        return list(events)

    THRESHOLD_MS = 3000

    flagged: list[types.LapEvent] = []
    for idx, ev in enumerate(events):
        delta = int(ev.lap_time_ms - median_ms) if ev.lap_time_ms is not None else None

        is_anomaly = delta is not None and delta > THRESHOLD_MS
        reason = None
        if is_anomaly:
            if ev.is_pit_in or ev.is_pit_out:
                reason = "pit_stop"
            elif ev.rainfall and not any(e.rainfall for e in events[:idx]):
                reason = "rain_onset"
            elif ev.track_status in (
                "4",
                "5",
                "6",
                "7",
            ):  # 4=VSC, 5=SC, 6=RED flag, 7=Yellow flag
                reason = "yellow_flag_vsc"
            else:
                reason = "unknown_slowlap"

        flagged.append(
            types.LapEvent(
                lap_number=ev.lap_number,
                lap_time_ms=ev.lap_time_ms,
                delta_to_median_ms=delta,
                sector1_ms=ev.sector1_ms,
                sector2_ms=ev.sector2_ms,
                sector3_ms=ev.sector3_ms,
                compound=ev.compound,
                stint=ev.stint,
                is_pit_in=ev.is_pit_in,
                is_pit_out=ev.is_pit_out,
                rainfall=ev.rainfall,
                track_status=ev.track_status,
                is_anomaly=is_anomaly,
                anomaly_reason=reason,
            )
        )
    return flagged


def inspect_lap_events(
    inp: types.InspectLapEventsInput,
) -> types.InspectLapEventsResult:
    """Flag every off-pace lap for the driver, with a compact reason."""

    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """ 
                        SELECT l.lap_number, l.lap_time_ms, l.s1_ms AS sector1_ms, l.s2_ms AS sector2_ms, l.s3_ms AS sector3_ms,
                                l.compound, l.stint, l.pit_in_time_ms, l.pit_out_time_ms, l.track_status, l.quali_segment, s.rainfall
                        FROM lap_times l
                        JOIN sessions s ON s.session_key = l.session_key
                        WHERE l.session_key = :sk
                        AND l.driver_number = :dn
                        AND l.deleted = FALSE
                        ORDER BY l.lap_number ASC """
                ),
                {"sk": inp.session_key, "dn": inp.driver_number},
            )
            .mappings()
            .all()
        )

    if not rows:
        raise types.NotFoundError(
            f"No laps found for driver : {inp.driver_number} in session : {inp.session_key}"
        )

    events = [
        types.LapEvent(
            lap_number=r["lap_number"],
            lap_time_ms=r["lap_time_ms"],
            delta_to_median_ms=None,
            sector1_ms=r["sector1_ms"],
            sector2_ms=r["sector2_ms"],
            sector3_ms=r["sector3_ms"],
            compound=r["compound"],
            stint=r["stint"],
            is_pit_in=r["pit_in_time_ms"] is not None,
            is_pit_out=r["pit_out_time_ms"] is not None,
            is_anomaly=False,
            rainfall=bool(r["rainfall"]),
            track_status=r["track_status"],
            quali_segment=r["quali_segment"],
        )
        for r in rows
    ]

    clean_times = [
        e.lap_time_ms
        for e in events
        if not e.is_pit_in and not e.is_pit_out and e.lap_time_ms is not None
    ]
    median_ms = int(statistics.median(clean_times)) if clean_times else 0

    flagged = tuple(_detect_lap_anomalies(events, median_ms))

    if inp.target_lap is not None:
        lo = inp.target_lap - inp.window_laps
        hi = inp.target_lap + inp.window_laps
        flagged = tuple(e for e in flagged if lo <= e.lap_number <= hi)

    return types.InspectLapEventsResult(
        session_key=inp.session_key,
        driver_number=inp.driver_number,
        target_lap=inp.target_lap,
        median_pace_ms=median_ms,
        events=flagged,
        anomaly_count=sum(1 for e in flagged if e.is_anomaly),
    )


def _find_cliff_lap(clean: list[dict], residuals_by_lap: dict) -> int | None:

    if len(clean) < 3:
        return None

    worst_lap_no = max(residuals_by_lap, key=residuals_by_lap.get)
    remainder = [lap for lap in clean if lap["lap_number"] != worst_lap_no]
    rx = [float(lap["lap_number"]) for lap in remainder]
    ry = [float(lap["lap_time_ms"]) for lap in remainder]
    rxm, rym = sum(rx) / len(rx), sum(ry) / len(ry)
    ss_xy = sum((x - rxm) * (y - rym) for x, y in zip(rx, ry))
    ss_xx = sum((x - rxm) ** 2 for x in rx)
    rbeta = ss_xy / ss_xx if ss_xx else 0.0
    ralpha = rym - rbeta * rxm

    candidate = next(lap for lap in clean if lap["lap_number"] == worst_lap_no)
    resid_candidate = float(candidate["lap_time_ms"]) - (ralpha + rbeta * worst_lap_no)

    other_resids = [
        float(lap["lap_time_ms"]) - (ralpha + rbeta * float(lap["lap_number"]))
        for lap in remainder
    ]
    sigma = (
        (sum(r * r for r in other_resids) / len(other_resids)) ** 0.5
        if other_resids
        else 0.0
    )
    CLIFF_MIN_MS = 1200.0
    if (sigma == 0.0 and resid_candidate > CLIFF_MIN_MS) or (
        sigma > 0.0 and resid_candidate > max(CLIFF_MIN_MS, 2.5 * sigma)
    ):
        return int(worst_lap_no)
    return None


def _compute_stint_degradation(laps: list[dict]) -> list[types.StintSummary]:
    """Fit LapTime(n) = alpha + beta * n per stint (ordinary least squares).

    alpha = pace at the start of the stint (ms)
    beta  = degradation slope (ms, positive = getting slower)"""

    if not laps:
        return []
    by_stint: dict[int, list[dict]] = {}
    for lap in laps:
        stint = lap["stint"]
        if stint is None:
            continue
        by_stint.setdefault(stint, []).append(lap)

    summaries = []
    for stint_idx in sorted(by_stint):
        stint_laps = sorted(by_stint[stint_idx], key=lambda lap: lap["lap_number"])

        clean = [
            lap
            for lap in stint_laps
            if lap["pit_in_time_ms"] is None
            and lap["pit_out_time_ms"] is None
            and lap["lap_time_ms"] is not None
        ]

        if len(clean) < 2:
            continue

        xs = [float(lap["lap_number"]) for lap in clean]
        ys = [float(lap["lap_time_ms"]) for lap in clean]
        x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
        ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        ss_xx = sum((x - x_mean) ** 2 for x in xs)
        beta = ss_xy / ss_xx if ss_xx else 0.0
        alpha = y_mean - beta * x_mean

        residuals = {x: y - (alpha + beta * x) for x, y in zip(xs, ys)}
        cliff_lap = _find_cliff_lap(clean, residuals)

        start_lap = clean[0]["lap_number"]
        points = tuple(
            types.StintLapPoint(
                lap_number=lap["lap_number"],
                tyre_age=lap["lap_number"] - start_lap + 1,
                lap_time_ms=int(lap["lap_time_ms"]),
            )
            for lap in clean
        )

        compound = clean[0]["compound"] or "UNKNOWN"
        summaries.append(
            types.StintSummary(
                stint_index=stint_idx,
                compound=compound,
                start_lap=start_lap,
                end_lap=clean[-1]["lap_number"],
                total_laps=len(clean),
                initial_pace_ms=round(alpha),
                final_pace_ms=round(alpha + beta * clean[-1]["lap_number"]),
                degradation_slope_ms_per_lap=round(beta, 2),
                cliff_detected=cliff_lap is not None,
                cliff_lap=cliff_lap,
                laps=points,
            )
        )
    return summaries


def stint_degradation_scanner(
    inp: types.StintDegradationInput,
) -> types.StintDegradationResult:
    """Scan all the driver's stints and compute the degradation slopes."""

    with extensions.engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """ 
                        SELECT lap_number, lap_time_ms, compound, stint, pit_in_time_ms, pit_out_time_ms
                        FROM lap_times
                        WHERE session_key = :sk
                        AND driver_number = :dn
                        AND deleted = FALSE
                        ORDER BY lap_number ASC
                    """
                ),
                {"sk": inp.session_key, "dn": inp.driver_number},
            )
            .mappings()
            .all()
        )

    if not rows:
        raise types.NotFoundError(
            f" No laps found for the driver : {inp.driver_number} for session : {inp.session_key}"
        )

    all_stints = _compute_stint_degradation([dict(r) for r in rows])
    if inp.stint_index is not None:
        all_stints = [s for s in all_stints if s.stint_index == inp.stint_index]

    worst = None
    worst_slope = -float("inf")
    for s in all_stints:
        if s.degradation_slope_ms_per_lap > worst_slope:
            worst_slope = s.degradation_slope_ms_per_lap
            worst = s.stint_index

    return types.StintDegradationResult(
        session_key=inp.session_key,
        driver_number=inp.driver_number,
        stints=tuple(all_stints),
        worst_degradation_stint=worst,
    )


def _parquet_rows(table) -> list[dict]:
    """Convert a pyarrow table into list-of-dicts, keeping only known channels."""
    WANTED = [
        "distance_m",
        "speed_kmh",
        "throttle",
        "brake",
        "gear",
        "drs",
        "x_pos",
        "y_pos",
    ]
    available = [c for c in WANTED if c in table.column_names]
    return [
        {col: table.column(col)[i].as_py() for col in available}
        for i in range(len(table))
    ]


def _read_artifact_full_channels(artifact: types.TelemetryArtifact) -> list[dict]:
    """Read the every channel form the artifact (parquet or json.gz)"""

    if artifact.storage_backend == "local" and artifact.format == "json.gz":
        path = Path(settings.telemetry_artifact_dir) / artifact.storage_key
        if not path.exists():
            raise types.DataError(f"artifact file not found : {path}")
        with gzip.open(path, "rb") as f:
            payload = json.loads(f.read().decode("utf-8"))
        return payload.get("samples", [])

    if artifact.storage_backend == "local" and artifact.format == "parquet":
        import pyarrow.parquet as pq

        path = Path(settings.telemetry_artifact_dir) / artifact.storage_key
        if not path.exists():
            raise types.DataError(f"artifact file not found : {path}")
        return _parquet_rows(pq.read_parquet(path))

    if artifact.storage_backend == "r2" and artifact.format == "parquet":
        import boto3
        import pyarrow.parquet as pq

        client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
        obj = client.get_object(
            Bucket=settings.telemetry_artifact_bucket,
            Key=artifact.storage_key,
        )
        return _parquet_rows(pq.read_table(io.BytesIO(obj["Body"].read())))

    raise types.DataError(
        f"unsupported artifact: {artifact.storage_backend}/{artifact.format}"
    )


def _to_sample_point(raw: dict) -> types.TelemetrySamplePoint:
    """Convert one raw artifact row into a validated TelemetrySamplePoint."""
    throttle = raw.get("throttle", 0.0) or 0.0
    if throttle <= 1.0:
        throttle *= 100.0

    return types.TelemetrySamplePoint(
        distance_m=float(raw.get("distance_m", 0.0) or 0.0),
        speed_kmh=float(raw.get("speed_kmh", 0.0) or 0.0),
        throttle_pct=round(throttle, 1),
        brake=bool(raw.get("brake", False)),
        gear=int(raw.get("gear", 0) or 0),
        drs=int(raw.get("drs", 0) or 0),
        x_pos=raw.get("x_pos"),
        y_pos=raw.get("y_pos"),
    )


def _resample_telemetry(
    samples: list[dict], max_points: int
) -> list[types.TelemetrySamplePoint]:
    """Downsample a lap to at most max_points points

    Raw telemetry logs once per ~0.3m (~18k points/lap) — too heavy for the
    API and the UI. We keep the SHAPE of the trace by picking, for each of
    max_points evenly-spaced distance targets, the sample closest to it.
    The first and last samples are always kept
    """

    if not samples:
        return []
    if max_points <= 1:
        return [_to_sample_point(samples[0])]
    ordered = sorted(samples, key=lambda s: s.get("distance_m", 0.0))
    if len(ordered) <= max_points:
        return [_to_sample_point(s) for s in ordered]

    first_d = ordered[0].get("distance_m", 0.0)
    last_d = ordered[-1].get("distance_m", 0.0)
    spacing = (last_d - first_d) / (max_points - 1)
    if spacing <= 0:
        return [_to_sample_point(p) for p in ordered]

    distances = [s.get("distance_m", 0.0) for s in ordered]

    picked: list[int] = []
    j = 0
    for k in range(max_points):
        target = first_d + spacing * k
        while j + 1 < len(distances) and abs(distances[j + 1] - target) <= abs(
            distances[j] - target
        ):
            j += 1
        if not picked or picked[-1] != j:
            picked.append(j)
    return [_to_sample_point(ordered[i]) for i in picked]


def _compute_trace_stats(
    samples: list[types.TelemetrySamplePoint],
) -> tuple[float, int]:
    if not samples:
        return 0.0, 0

    total_d = samples[-1].distance_m - samples[0].distance_m
    if total_d <= 0:
        return 0.0, 0

    throttle_d = sum(
        samples[i + 1].distance_m - samples[i].distance_m
        for i in range(len(samples) - 1)
        if samples[i].throttle_pct >= 99.0
    )
    full_throttle_pct = round(throttle_d / total_d * 100, 1)

    braking = sum(
        1
        for i in range(1, len(samples))
        if samples[i].brake and not samples[i - 1].brake
    )
    return full_throttle_pct, braking


MAX_LAPS_PER_CALL = 12


def telemetry_inspector(
    inp: types.TelemetryInspectorInput,
) -> types.TelemetryInspectorResult:
    """Load the full telemetry for (driver, laps)
    Flow: find artifact metadata in Postgres -> read channels from storage -> resample -> compute stats.
    """
    if not inp.lap_numbers:
        raise types.DataError("lap_numbers is required for telemetry inspector")

    driver_laps: dict[int, list[int]] = {inp.driver_number: list(inp.lap_numbers)}

    if inp.compare_driver_number is not None:
        driver_laps.setdefault(inp.compare_driver_number, []).extend(
            inp.compare_lap_numbers
        )

    artifacts_by_key: dict[tuple[int, int], types.TelemetryArtifact] = {}

    if sum(len(laps) for laps in driver_laps.values()) > MAX_LAPS_PER_CALL:
        raise types.DataError(
            f"telemetry_inspector rejects {sum(len(laps) for laps in driver_laps.values())} laps, cap is {MAX_LAPS_PER_CALL}"
        )

    for drv_num, laps in driver_laps.items():
        if not laps:
            continue
        for a in get_lap_telemetry_artifacts(
            types.GetLapTelemetryArtifactsInput(
                session_key=inp.session_key,
                driver_number=drv_num,
                lap_numbers=tuple(laps),
            )
        ).artifacts:
            artifacts_by_key[(a.driver_number, a.lap_number)] = a

    abbrev_map: dict[int, str] = {}
    with extensions.engine.connect() as conn:
        drv_rows = (
            conn.execute(
                text(
                    "SELECT driver_number, abbreviation FROM drivers "
                    "WHERE session_key = :sk AND driver_number = ANY(:dns)"
                ),
                {"sk": inp.session_key, "dns": list(driver_laps.keys())},
            )
            .mappings()
            .all()
        )
        for r in drv_rows:
            abbrev_map[r["driver_number"]] = r["abbreviation"]

    traces: list[types.TelemetryLapTrace] = []
    for drv_num, laps in driver_laps.items():
        for lap_num in laps:
            artifact = artifacts_by_key.get((drv_num, lap_num))
            if artifact is None:
                continue  # missing lap is skipped; the others may still render
            raw = _read_artifact_full_channels(artifact)
            traces.append(
                types.TelemetryLapTrace(
                    driver_number=drv_num,
                    driver_abbreviation=abbrev_map.get(drv_num, "???"),
                    lap_number=lap_num,
                    samples=tuple(_resample_telemetry(raw, inp.max_samples_per_lap)),
                )
            )

    if not traces:
        raise types.DataError("no telemetry artifacts found for the requested laps")

    primary = traces[0]
    full_throttle_pct, braking_zones = _compute_trace_stats(list(primary.samples))

    speed_delta_apex = None
    if len(traces) >= 2:
        apex_a = min(
            (s.speed_kmh for s in traces[0].samples if s.speed_kmh > 0),
            default=None,
        )
        apex_b = min(
            (s.speed_kmh for s in traces[1].samples if s.speed_kmh > 0),
            default=None,
        )
        if apex_a is not None and apex_b is not None:
            speed_delta_apex = round(apex_b - apex_a, 2)

    return types.TelemetryInspectorResult(
        session_key=inp.session_key,
        traces=tuple(traces),
        speed_delta_apex_kmh=speed_delta_apex,
        full_throttle_pct=full_throttle_pct,
        heavy_braking_zones_count=braking_zones,
    )


def _assess(checks: list[types.EvidenceCheck]) -> types.VerifyEvidenceResult:
    """Pure verdict: any failed check becomes a refusal with a readable reason."""
    failed = [c for c in checks if not c.passed]
    if not failed:
        return types.VerifyEvidenceResult(passed=True, checks=tuple(checks))
    reasons = "; ".join(f"{c.name}: {c.detail or 'failed'}" for c in failed)
    return types.VerifyEvidenceResult(
        passed=False,
        checks=tuple(checks),
        refusal_reason=reasons,
    )


def verify_evidence(inp: types.VerifyEvidenceInput) -> types.VerifyEvidenceResult:
    """Check the evidence exists before we trust the computed answer.

    required_tool_names is reserved for the planner trace (Lesson 5+).
    """
    checks: list[types.EvidenceCheck] = []

    with extensions.engine.connect() as conn:
        session_found = (
            conn.execute(
                text("SELECT 1 FROM sessions WHERE session_key = :sk LIMIT 1"),
                {"sk": inp.session_key},
            ).first()
            is not None
        )
        checks.append(
            types.EvidenceCheck(
                "session_exists", session_found, detail=f"session {inp.session_key}"
            )
        )

        driver_found = (
            conn.execute(
                text(
                    "SELECT 1 FROM drivers WHERE session_key = :sk AND driver_number = :dn LIMIT 1"
                ),
                {"sk": inp.session_key, "dn": inp.driver_number},
            ).first()
            is not None
        )
        checks.append(
            types.EvidenceCheck(
                "driver_exists", driver_found, detail=f"driver {inp.driver_number}"
            )
        )

    if inp.required_laps:
        artifacts = get_lap_telemetry_artifacts(
            types.GetLapTelemetryArtifactsInput(
                session_key=inp.session_key,
                driver_number=inp.driver_number,
                lap_numbers=inp.required_laps,
            )
        ).artifacts
        found_laps = {a.lap_number for a in artifacts}
        missing = sorted(set(inp.required_laps) - found_laps)
        checks.append(
            types.EvidenceCheck(
                "artifacts_cover_required_laps",
                not missing,
                detail=f"missing laps {missing}"
                if missing
                else "all required laps present",
            )
        )

    return _assess(checks)


_TRAIT_FEATURES = (
    "braking_aggression",
    "drs_usage_pct",
    "max_speed_capability",
    "avg_speed_trap",
    "lap_time_consistency",
)
_TRAIT_LABELS = {
    "braking_aggression": "Brake aggression",
    "drs_usage_pct": "DRS usage",
    "max_speed_capability": "Top speed",
    "avg_speed_trap": "Trap speed",
    "lap_time_consistency": "Consistency",
}

_STYLE_ROWS_SQL = text("""
        SELECT e.driver_number, e.season, e.abbreviation,
            COALESCE(f.full_name, e.abbreviation) AS full_name,
            e.archetype,
            f.braking_aggression, f.drs_usage_pct, f.max_speed_capability,
            f.avg_speed_trap, f.lap_time_consistency
        FROM driver_embeddings e
        LEFT JOIN driver_features f
        ON f.driver_number = e.driver_number AND f.season = e.season
        WHERE e.season = :season
        ORDER BY e.driver_number
""")


def _percentile_rank(value: float | None, values: list[float | None]) -> float | None:
    """Percentile rank (0-100) of value within values; None if value is None."""
    if value is None:
        return None
    present = sorted(v for v in values if v is not None)
    if not present:
        return None
    return (sum(1 for v in present if v <= value) / len(present)) * 100.0


def _match_driver(rows, name: str):
    """Match a user's name against full_name / abbreviation / driver number."""
    target = (name or "").strip().lower()
    if not target:
        return None
    for row in rows:
        if (
            target == str(row["abbreviation"]).lower()
            or target == str(row["full_name"]).lower()
            or target == str(row["driver_number"])
        ):
            return row
    for row in rows:
        if (
            target in str(row["full_name"]).lower()
            or target in str(row["abbreviation"]).lower()
        ):
            return row
    return None


def _build_style_summary(
    primary: types.DriverStyleProfile | None, compare: types.DriverStyleProfile | None
) -> str:
    if primary is None:
        return "Could not find the requested driver in the style model."
    if compare is None:
        top = primary.traits[0] if primary.traits else None
        base = f"{primary.full_name} is classified as a {primary.archetype}."
        if top is not None:
            base += (
                f" Their most distinct trait is {top.label} "
                f"({top.percentile:.0f}th percentile of the field)."
            )
        return base
    largest = None
    for p in primary.traits:
        c = next((t for t in compare.traits if t.feature == p.feature), None)
        if c is not None and (
            largest is None
            or abs(p.percentile - c.percentile) > abs(largest[0] - largest[1])
        ):
            largest = (p.percentile, c.percentile, p.label)
    text = (
        f"{primary.full_name} is a {primary.archetype}; "
        f"{compare.full_name} is a {compare.archetype}."
    )
    if largest is not None:
        text += (
            f" The largest style gap is in {largest[2]} "
            f"({largest[0]:.0f}th vs {largest[1]:.0f}nd percentile)."
        )
    return text


def driver_style_compare(inp: types.DriverStyleCompareInput) -> types.DriverStyleResult:
    """Compare two drivers' PCA/K-Means archetypes + trait percentiles."""
    with extensions.engine.connect() as conn:
        if not inp.year:
            row = (
                conn.execute(
                    text("SELECT COALESCE(MAX(season), 0) AS s FROM driver_embeddings")
                )
                .mappings()
                .all()
            )
            season = int(row[0]["s"]) if row else 0
        else:
            season = inp.year
        rows = conn.execute(_STYLE_ROWS_SQL, {"season": season}).mappings().all()

    if season == 0 or not rows:
        return types.DriverStyleResult(
            season=season,
            field_size=0,
            driver=None,
            summary="No driver style data is available yet. Run the clustering job first.",
        )

    def _profile(name: str) -> types.DriverStyleProfile | None:
        row = _match_driver(rows, name)
        if row is None:
            return None
        traits = []
        for feature in _TRAIT_FEATURES:
            value = row[feature]
            if value is None:
                continue
            traits.append(
                types.DriverStyleTrait(
                    feature=feature,
                    label=_TRAIT_LABELS[feature],
                    percentile=_percentile_rank(value, [r[feature] for r in rows])
                    or 0.0,
                    value=float(value),
                )
            )
        return types.DriverStyleProfile(
            driver_number=int(row["driver_number"]),
            full_name=row["full_name"],
            abbreviation=row["abbreviation"],
            archetype=row["archetype"],
            traits=tuple(traits),
        )

    primary = _profile(inp.driver_name)
    compare = _profile(inp.compare_driver_name) if inp.compare_driver_name else None
    return types.DriverStyleResult(
        season=season,
        field_size=len(rows),
        driver=primary,
        compare=compare,
        summary=_build_style_summary(primary, compare),
    )


# ---------------------------------------------------------------------------
# Task 5 -- Exact Data Catalog. These answer "what data do you have?" straight
# from PostgreSQL. Availability questions must never fall through to RAG.
# ---------------------------------------------------------------------------


def _catalog_entry(row) -> types.SessionCatalogEntry:
    return types.SessionCatalogEntry(
        session_key=row["session_key"],
        year=row["year"],
        gp_name=row["gp_name"],
        country=row["country"],
        session_type=row["session_type"],
        session_name=row["session_name"],
        date_start=str(row["date_start"]) if row["date_start"] is not None else None,
    )


def list_available_sessions(
    inp: types.ListAvailableSessionsInput,
) -> types.SessionCatalogResult:
    """List stored sessions, optionally filtered by year/GP/country/session type."""
    limit = max(1, min(int(inp.limit), _MAX_CATALOG_LIMIT))
    sql = """
        SELECT session_key, year, gp_name, country, session_type, session_name, date_start
        FROM sessions
        WHERE 1 = 1
    """
    binds: dict = {}
    if inp.year is not None:
        sql += " AND year = :year"
        binds["year"] = inp.year
    if inp.gp_name:
        sql += " AND (gp_name ILIKE :gp OR country ILIKE :gp)"
        binds["gp"] = f"%{inp.gp_name.strip()}%"
    if inp.country:
        sql += " AND country ILIKE :country"
        binds["country"] = f"%{inp.country.strip()}%"
    if inp.session_type is not None:
        sql += " AND session_type = :stype"
        binds["stype"] = inp.session_type.value
    sql += " ORDER BY year DESC, date_start DESC NULLS LAST LIMIT :lim"
    binds["lim"] = limit

    with extensions.engine.connect() as conn:
        rows = conn.execute(text(sql), binds).mappings().all()

    entries = tuple(_catalog_entry(r) for r in rows)
    return types.SessionCatalogResult(sessions=entries, total=len(entries))


def search_sessions(inp: types.SearchSessionsInput) -> types.SessionCatalogResult:
    """Free-text session lookup by GP/country/session name via SQL ILIKE.

    This is the deterministic fallback for partial race names. It never calls the
    vector store: availability is a fact about Postgres, not a semantic match.
    """
    limit = max(1, min(int(inp.limit), _MAX_CATALOG_LIMIT))
    term = inp.query.strip()
    sql = """
        SELECT session_key, year, gp_name, country, session_type, session_name, date_start
        FROM sessions
        WHERE 1 = 1
    """
    binds: dict = {}
    if term:
        sql += " AND (gp_name ILIKE :q OR country ILIKE :q OR session_name ILIKE :q)"
        binds["q"] = f"%{term}%"
    if inp.year is not None:
        sql += " AND year = :year"
        binds["year"] = inp.year
    if inp.session_type is not None:
        sql += " AND session_type = :stype"
        binds["stype"] = inp.session_type.value
    sql += " ORDER BY year DESC, date_start DESC NULLS LAST LIMIT :lim"
    binds["lim"] = limit

    with extensions.engine.connect() as conn:
        rows = conn.execute(text(sql), binds).mappings().all()

    entries = tuple(_catalog_entry(r) for r in rows)
    return types.SessionCatalogResult(sessions=entries, total=len(entries), query=term)


def _scalar(conn, sql: str, binds: dict) -> int:
    return int(conn.execute(text(sql), binds).scalar() or 0)


def describe_session_coverage(
    inp: types.DescribeSessionCoverageInput,
) -> types.DescribeSessionCoverageResult:
    """Report exactly which datasets exist for a session (counts, not guesses)."""
    binds = {"sk": inp.session_key}
    with extensions.engine.connect() as conn:
        session_row = (
            conn.execute(
                text("SELECT rainfall FROM sessions WHERE session_key = :sk"), binds
            )
            .mappings()
            .first()
        )
        if session_row is None:
            raise types.NotFoundError(f"Session {inp.session_key} not found")

        lap_stats = (
            conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS laps, COUNT(DISTINCT driver_number) AS drivers
                    FROM lap_times
                    WHERE session_key = :sk AND deleted = FALSE
                    """
                ),
                binds,
            )
            .mappings()
            .first()
        )
        lap_count = int(lap_stats["laps"] or 0)
        driver_count = int(lap_stats["drivers"] or 0)
        telemetry_count = _scalar(
            conn,
            "SELECT COUNT(*) FROM telemetry_artifacts WHERE session_key = :sk",
            binds,
        )
        weather_count = _scalar(
            conn, "SELECT COUNT(*) FROM weather_events WHERE session_key = :sk", binds
        )
        weather_rain = _scalar(
            conn,
            "SELECT COUNT(*) FROM weather_events WHERE session_key = :sk AND rainfall IS TRUE",
            binds,
        )
        race_control_count = _scalar(
            conn,
            "SELECT COUNT(*) FROM race_control_events WHERE session_key = :sk",
            binds,
        )
        radio_count = _scalar(
            conn, "SELECT COUNT(*) FROM team_radio WHERE session_key = :sk", binds
        )
        has_docs_table = conn.execute(
            text("SELECT to_regclass('public.strategy_documents')")
        ).scalar()
        indexed_count = (
            _scalar(
                conn,
                "SELECT COUNT(*) FROM strategy_documents WHERE session_key = :sk",
                binds,
            )
            if has_docs_table
            else 0
        )

    has_rainfall = bool(session_row["rainfall"]) or weather_rain > 0
    coverage = types.SessionCoverage(
        session_key=inp.session_key,
        has_laps=lap_count > 0,
        lap_count=lap_count,
        driver_count=driver_count,
        has_telemetry=telemetry_count > 0,
        telemetry_artifact_count=telemetry_count,
        has_weather=weather_count > 0,
        weather_sample_count=weather_count,
        has_race_control=race_control_count > 0,
        race_control_count=race_control_count,
        has_radio=radio_count > 0,
        radio_clip_count=radio_count,
        has_indexed_documents=indexed_count > 0,
        indexed_document_count=indexed_count,
        has_rainfall=has_rainfall,
    )
    return types.DescribeSessionCoverageResult(coverage=coverage)


# ---------------------------------------------------------------------------
# Task 6 -- Deterministic strategy analysis. Pit loss is measured from stored
# lap times; scenarios are a bounded named set. Nothing here is an LLM guess.
# ---------------------------------------------------------------------------


def _flags_by_lap(conn, session_key: int) -> dict[int, list[str]]:
    rows = (
        conn.execute(
            text(
                """
            SELECT lap_number, flag
            FROM race_control_events
            WHERE session_key = :sk AND lap_number IS NOT NULL
            """
            ),
            {"sk": session_key},
        )
        .mappings()
        .all()
    )
    flags: dict[int, list[str]] = {}
    for r in rows:
        flags.setdefault(int(r["lap_number"]), []).append(r["flag"] or "")
    return flags


def estimate_pit_loss(inp: types.EstimatePitLossInput) -> types.EstimatePitLossResult:
    """Measure observed pit loss (in+out lap vs clean laps) grouped by condition."""
    binds: dict = {"sk": inp.session_key}
    sql = """
        SELECT driver_number, lap_number, lap_time_ms, pit_in_time_ms,
               pit_out_time_ms, compound, stint
        FROM lap_times
        WHERE session_key = :sk AND deleted = FALSE
    """
    if inp.driver_number is not None:
        sql += " AND driver_number = :dn"
        binds["dn"] = inp.driver_number
    sql += " ORDER BY driver_number ASC, lap_number ASC"

    with extensions.engine.connect() as conn:
        rows = conn.execute(text(sql), binds).mappings().all()
        flags_by_lap = _flags_by_lap(conn, inp.session_key)

    if not rows:
        raise types.NotFoundError(f"No lap data for session {inp.session_key}")

    laps_by_driver: dict[int, list[dict]] = {}
    for r in rows:
        laps_by_driver.setdefault(int(r["driver_number"]), []).append(dict(r))

    def _is_green(lap_number: int) -> bool:
        return (
            strategy.classify_pit_condition(flags_by_lap.get(lap_number, [])) == "green"
        )

    clean_times = [
        float(r["lap_time_ms"])
        for r in rows
        if r["lap_time_ms"] is not None
        and r["pit_in_time_ms"] is None
        and r["pit_out_time_ms"] is None
        and _is_green(int(r["lap_number"]))
    ]
    baseline = (
        int(round(statistics.median(clean_times))) if len(clean_times) >= 3 else None
    )

    records: list[tuple[str, int | None]] = []
    for driver_laps in laps_by_driver.values():
        by_lap = {int(lap["lap_number"]): lap for lap in driver_laps}
        for stop in _derive_pit_stops(driver_laps):
            lap_in = by_lap.get(stop.pit_in_lap)
            lap_out = by_lap.get(stop.pit_out_lap)
            if lap_in is None or lap_out is None:
                continue
            loss = strategy.pit_loss_ms(
                lap_in["lap_time_ms"], lap_out["lap_time_ms"], baseline
            )
            condition = strategy.classify_pit_condition(
                flags_by_lap.get(stop.pit_in_lap, [])
                + flags_by_lap.get(stop.pit_out_lap, [])
            )
            records.append((condition, loss))

    estimates = strategy.summarize_pit_losses(records)
    assumption = (
        f"pit loss = (in-lap + out-lap) - 2 x clean-lap median"
        f" ({baseline} ms); measured from {len(clean_times)} clean green laps"
        if baseline is not None
        else "not enough clean green laps to establish a baseline; pit loss unavailable"
    )
    return types.EstimatePitLossResult(
        session_key=inp.session_key,
        estimates=estimates,
        baseline_clean_lap_ms=baseline,
        assumption=assumption,
    )


def _pit_loss_for(
    estimates: tuple[types.PitLossEstimate, ...], condition: str
) -> int | None:
    for est in estimates:
        if est.condition == condition:
            return est.mean_pit_loss_ms
    return None


def compare_strategy_scenarios(
    inp: types.CompareStrategyScenariosInput,
) -> types.CompareStrategyScenariosResult:
    """Compare stay-out vs pit-now scenarios using measured degradation + pit loss."""
    pit = estimate_pit_loss(
        types.EstimatePitLossInput(
            session_key=inp.session_key, driver_number=inp.driver_number
        )
    )
    stints = stint_degradation_scanner(
        types.StintDegradationInput(
            session_key=inp.session_key, driver_number=inp.driver_number
        )
    )
    race_control = fetch_race_control_window(
        types.RaceControlWindowInput(session_key=inp.session_key)
    )
    weather = fetch_weather_window(
        types.WeatherWindowInput(session_key=inp.session_key)
    )

    with extensions.engine.connect() as conn:
        lap_rows = (
            conn.execute(
                text(
                    """
                SELECT lap_number, stint, compound
                FROM lap_times
                WHERE session_key = :sk AND driver_number = :dn AND deleted = FALSE
                ORDER BY lap_number ASC
                """
                ),
                {"sk": inp.session_key, "dn": inp.driver_number},
            )
            .mappings()
            .all()
        )
        total_laps = conn.execute(
            text("SELECT MAX(lap_number) FROM lap_times WHERE session_key = :sk"),
            {"sk": inp.session_key},
        ).scalar()

    if not lap_rows:
        raise types.NotFoundError(
            f"Driver {inp.driver_number} has no laps in session {inp.session_key}"
        )

    driver_laps = [dict(r) for r in lap_rows]
    current_lap = inp.current_lap or max(int(r["lap_number"]) for r in driver_laps)
    total_laps = int(total_laps) if total_laps is not None else None
    remaining_laps = (
        max(total_laps - current_lap, 0)
        if total_laps is not None and current_lap is not None
        else None
    )

    active = next(
        (s for s in stints.stints if s.start_lap <= current_lap <= s.end_lap),
        stints.stints[-1] if stints.stints else None,
    )
    compound = active.compound if active else None
    slope = active.degradation_slope_ms_per_lap if active else None

    pit_green = _pit_loss_for(pit.estimates, "green")
    pit_vsc = _pit_loss_for(pit.estimates, "vsc")
    pit_sc = _pit_loss_for(pit.estimates, "sc")

    scenarios, assumptions, notes = strategy.build_scenarios(
        current_lap=current_lap,
        total_laps=total_laps,
        remaining_laps=remaining_laps,
        compound=compound,
        degradation_slope_ms_per_lap=slope,
        pit_loss_green_ms=pit_green,
        pit_loss_vsc_ms=pit_vsc,
        pit_loss_sc_ms=pit_sc,
        rain_in_session=weather.rainfall_laps > 0,
        safety_car_periods=race_control.safety_car_periods,
    )

    assumptions.insert(0, pit.assumption)
    try:
        gap = gap_and_position_snapshot(
            types.GapPositionInput(
                session_key=inp.session_key,
                driver_number=inp.driver_number,
                target_lap=current_lap,
            )
        )
        if gap.car_behind_gap_ms is not None:
            notes.append(
                f"car behind ({gap.car_behind_number}) is "
                f"{gap.car_behind_gap_ms} ms back at lap {gap.lap_number}: "
                f"undercut exposure."
            )
        else:
            notes.append("no car directly behind at the target lap (traffic-free).")
    except types.AgentError:
        notes.append("track-position context unavailable at the target lap.")

    return types.CompareStrategyScenariosResult(
        session_key=inp.session_key,
        driver_number=inp.driver_number,
        current_lap=current_lap,
        total_laps=total_laps,
        remaining_laps=remaining_laps,
        compound=compound,
        degradation_slope_ms_per_lap=slope,
        pit_loss_green_ms=pit_green,
        pit_loss_vsc_ms=pit_vsc,
        pit_loss_sc_ms=pit_sc,
        rain_in_session=weather.rainfall_laps > 0,
        safety_car_periods=race_control.safety_car_periods,
        scenarios=tuple(scenarios),
        assumptions=tuple(assumptions),
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Task 8 -- RAG over approved strategy documents. Qualitative sources only:
# this tool never answers availability and never supplies numeric telemetry.
# ---------------------------------------------------------------------------


def _source_excerpt(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= _SOURCE_EXCERPT_CHARS:
        return cleaned
    return cleaned[: _SOURCE_EXCERPT_CHARS - 1].rstrip() + "\u2026"


def search_strategy_sources(
    inp: types.SearchStrategySourcesInput,
) -> types.SearchStrategySourcesResult:
    """Retrieve approved document chunks for a qualitative question."""
    query = inp.query.strip()
    if not query:
        raise types.DataError("search_strategy_sources requires a query")

    limit = max(1, min(int(inp.limit), _MAX_SOURCE_LIMIT))
    source_types = [s for s in inp.source_types if s] or None

    try:
        hits = vector_store.search(
            query,
            source_types=source_types,
            year=inp.year,
            session_key=inp.session_key,
            driver_number=inp.driver_number,
            limit=limit,
        )
    except vector_store.VectorStoreError as exc:
        # Retrieval failure must never block deterministic answers elsewhere.
        return types.SearchStrategySourcesResult(
            query=query,
            hits=(),
            degraded=True,
            note=f"source retrieval unavailable: {exc}",
        )

    if not hits:
        return types.SearchStrategySourcesResult(query=query, hits=())

    records = {
        record.chunk_id: record
        for record in strategy_documents.hydrate_chunks([h.chunk_id for h in hits])
    }
    sources: list[types.StrategySourceHit] = []
    for hit in hits:
        record = records.get(hit.chunk_id)
        if record is None:
            # Missing or no longer approved -> never display it.
            continue
        sources.append(
            types.StrategySourceHit(
                document_id=record.document_id,
                chunk_id=record.chunk_id,
                title=record.title,
                source_type=record.source_type,
                excerpt=_source_excerpt(record.text),
                source_url=record.source_url,
                r2_key=record.r2_key,
                page_number=record.page_number,
                timestamp_from_ms=record.timestamp_from_ms,
                timestamp_to_ms=record.timestamp_to_ms,
                score=hit.score,
            )
        )
    return types.SearchStrategySourcesResult(query=query, hits=tuple(sources))
