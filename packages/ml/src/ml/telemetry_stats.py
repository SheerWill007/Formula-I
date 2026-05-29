"""
Pre-compute telemetry statistics from raw telemetry data.

Run after ingestion to populate lap_telemetry_stats.
Safe to rerun — uses DELETE-then-INSERT per session.

Usage:
    uv run python -m ml.telemetry_stats --session-key 9554
    uv run python -m ml.telemetry_stats --all   # process all sessions
"""

from __future__ import annotations
import argparse
import json
from typing import Optional
import numpy as np
from sqlalchemy import create_engine, text
from ml.config import settings
import structlog

log = structlog.get_logger()


def get_engine():
    return create_engine(settings.database_url)


# ── Corner detection ──────────────────────────────────────────────────────────


def detect_corners(
    distances: list[float],
    speeds: list[float],
    min_gap_m: float = 150.0,
    min_drop: float = 20.0,
) -> list[int]:
    """
    Return indices of corner apexes (local speed minima).

    min_gap_m:  minimum metres between corners (avoids double-counting chicanes)
    min_drop:   minimum speed reduction vs local max before (filters DRS lifts)
    """
    apexes = []
    n = len(speeds)

    for i in range(2, n - 2):
        # Must be a local minimum over ±2 samples
        if not (speeds[i] <= speeds[i - 1] and speeds[i] <= speeds[i + 1]):
            continue
        if not (speeds[i] <= speeds[i - 2] and speeds[i] <= speeds[i + 2]):
            continue

        # Speed must have dropped meaningfully from recent local max
        lookback = max(0, i - 30)
        local_max = max(speeds[lookback:i]) if lookback < i else speeds[i]
        if local_max - speeds[i] < min_drop:
            continue

        # Enforce minimum gap between corners
        if apexes and distances[i] - distances[apexes[-1]] < min_gap_m:
            # Keep the slower one (deeper corner)
            if speeds[i] < speeds[apexes[-1]]:
                apexes[-1] = i
            continue

        apexes.append(i)

    return apexes


def analyse_corner(
    idx: int,
    distances: list[float],
    speeds: list[float],
    brakes: list[bool],
    throttles: list[float],
    gears: list[int],
    rpms: list[float],
    window: int = 40,
) -> dict:
    """Extract corner metrics around an apex index."""
    n = len(speeds)
    start = max(0, idx - window)
    end = min(n - 1, idx + window)

    # Entry speed — max in window before apex
    entry_speed = max(speeds[start:idx]) if idx > start else speeds[idx]

    # Exit speed — max in window after apex
    exit_speed = max(speeds[idx:end]) if end > idx else speeds[idx]

    # Brake point — last sample where brake=True before apex (farthest from apex)
    brake_point_m = None
    for j in range(idx - 1, start - 1, -1):
        if brakes[j]:
            brake_point_m = distances[j]
            break

    # Throttle application point — first sample where throttle > 10% after apex
    throttle_point_m = None
    for j in range(idx, end):
        if (throttles[j] or 0) > 10:
            throttle_point_m = distances[j]
            break

    return {
        "distance_m": round(distances[idx], 1),
        "min_speed_kmh": round(speeds[idx], 1),
        "entry_speed_kmh": round(entry_speed, 1),
        "exit_speed_kmh": round(exit_speed, 1),
        "brake_point_m": round(brake_point_m, 1) if brake_point_m else None,
        "throttle_point_m": round(throttle_point_m, 1) if throttle_point_m else None,
        "min_gear": gears[idx],
        "apex_rpm": int(rpms[idx]) if rpms[idx] else None,
    }


# ── Speed trap detection ──────────────────────────────────────────────────────


def find_speed_traps(
    distances: list[float],
    speeds: list[float],
    drs: list[int],
) -> tuple[Optional[float], Optional[float], float]:
    """
    Find speed trap values.
    Returns (trap1_kmh, trap2_kmh, max_kmh).

    Speed traps are located in DRS zones — high speed sections.
    We find up to 2 distinct DRS zones and take peak speed in each.
    """
    max_speed = max(speeds)

    # Find DRS open zones
    drs_zones: list[tuple[int, int]] = []
    in_zone = False
    zone_start = 0

    for i, d in enumerate(drs):
        if (d or 0) > 8 and not in_zone:
            in_zone = True
            zone_start = i
        elif (d or 0) <= 8 and in_zone:
            in_zone = False
            if i - zone_start > 5:  # at least 5 samples long
                drs_zones.append((zone_start, i))

    if not drs_zones:
        # No DRS data — use highest speed point and halfway point
        mid = len(speeds) // 2
        return (
            round(max(speeds[:mid]), 1),
            round(max(speeds[mid:]), 1),
            round(max_speed, 1),
        )

    trap1 = (
        round(max(speeds[drs_zones[0][0] : drs_zones[0][1]]), 1)
        if len(drs_zones) >= 1
        else None
    )
    trap2 = (
        round(max(speeds[drs_zones[1][0] : drs_zones[1][1]]), 1)
        if len(drs_zones) >= 2
        else None
    )

    return trap1, trap2, round(max_speed, 1)


# ── Main computation ──────────────────────────────────────────────────────────


def compute_stats_for_session(session_key: int) -> int:
    """
    Compute lap_telemetry_stats for all drivers in a session.
    Returns number of rows written.
    """
    engine = get_engine()
    rows_written = 0

    with engine.connect() as conn:
        # Get all driver/lap combos with enough telemetry samples
        driver_laps = (
            conn.execute(
                text("""
            SELECT driver_number, lap_number, COUNT(*) as samples
            FROM telemetry
            WHERE session_key = :sk
            GROUP BY driver_number, lap_number
            HAVING COUNT(*) >= 50
            ORDER BY driver_number, lap_number
        """),
                {"sk": session_key},
            )
            .mappings()
            .all()
        )

        if not driver_laps:
            log.warning("stats.no_telemetry", session_key=session_key)
            return 0

        # Clear existing stats for this session
        conn.execute(
            text("DELETE FROM lap_telemetry_stats WHERE session_key = :sk"),
            {"sk": session_key},
        )

        for dl in driver_laps:
            dn = dl["driver_number"]
            ln = dl["lap_number"]

            rows = (
                conn.execute(
                    text("""
                SELECT distance_m, speed_kmh, brake, gear,
                       throttle_pct, rpm, drs
                FROM telemetry
                WHERE session_key   = :sk
                  AND driver_number = :dn
                  AND lap_number    = :ln
                ORDER BY distance_m ASC NULLS LAST, sample_order
            """),
                    {"sk": session_key, "dn": dn, "ln": ln},
                )
                .mappings()
                .all()
            )

            if not rows:
                continue

            distances = [r["distance_m"] or 0.0 for r in rows]
            speeds = [r["speed_kmh"] or 0.0 for r in rows]
            brakes = [bool(r["brake"]) for r in rows]
            throttles = [r["throttle_pct"] or 0.0 for r in rows]
            gears = [r["gear"] or 1 for r in rows]
            rpms = [r["rpm"] or 0.0 for r in rows]
            drs_vals = [r["drs"] or 0 for r in rows]

            # Corner analysis
            apex_indices = detect_corners(distances, speeds)
            corners = []
            for i, apex_idx in enumerate(apex_indices):
                corner = analyse_corner(
                    apex_idx, distances, speeds, brakes, throttles, gears, rpms
                )
                corner["corner_num"] = i + 1
                corners.append(corner)

            # Speed traps
            trap1, trap2, max_spd = find_speed_traps(distances, speeds, drs_vals)

            # RPM stats
            valid_rpms = [r for r in rpms if r > 0]
            max_rpm = int(max(valid_rpms)) if valid_rpms else None
            avg_rpm = float(np.mean(valid_rpms)) if valid_rpms else None
            avg_rpm_pct = (
                round(avg_rpm / max_rpm * 100, 1) if avg_rpm and max_rpm else None
            )

            # Braking aggression — avg distance before apex where driver brakes
            brake_distances = []
            for corner in corners:
                if corner["brake_point_m"] and corner["distance_m"]:
                    gap = corner["distance_m"] - corner["brake_point_m"]
                    if gap > 0:
                        brake_distances.append(gap)
            avg_brake_dist = (
                round(float(np.mean(brake_distances)), 1) if brake_distances else None
            )

            # DRS open percentage
            drs_open_count = sum(1 for d in drs_vals if d > 8)
            drs_open_pct = (
                round(drs_open_count / len(drs_vals) * 100, 1) if drs_vals else None
            )

            conn.execute(
                text("""
                INSERT INTO lap_telemetry_stats (
                    session_key, driver_number, lap_number,
                    corners,
                    speed_trap_1_kmh, speed_trap_2_kmh, max_speed_kmh,
                    max_rpm, avg_rpm_pct,
                    avg_brake_point_pct,
                    drs_open_pct,
                    computed_at
                ) VALUES (
                    :session_key, :driver_number, :lap_number,
                    :corners,
                    :trap1, :trap2, :max_spd,
                    :max_rpm, :avg_rpm_pct,
                    :avg_brake_dist,
                    :drs_open_pct,
                    NOW()
                )
            """),
                {
                    "session_key": session_key,
                    "driver_number": dn,
                    "lap_number": ln,
                    "corners": json.dumps(corners),
                    "trap1": trap1,
                    "trap2": trap2,
                    "max_spd": max_spd,
                    "max_rpm": max_rpm,
                    "avg_rpm_pct": avg_rpm_pct,
                    "avg_brake_dist": avg_brake_dist,
                    "drs_open_pct": drs_open_pct,
                },
            )
            rows_written += 1

        conn.commit()

    log.info("stats.computed", session_key=session_key, rows=rows_written)
    return rows_written


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--session-key", type=int)
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    engine = get_engine()

    if args.all:
        with engine.connect() as conn:
            keys = (
                conn.execute(
                    text("""
                SELECT DISTINCT session_key FROM telemetry
                ORDER BY session_key
            """)
                )
                .scalars()
                .all()
            )
        for sk in keys:
            count = compute_stats_for_session(sk)
            print(f"  session {sk}: {count} rows written")
    else:
        count = compute_stats_for_session(args.session_key)
        print(f"\n✅  {count} driver/lap stats computed for session {args.session_key}")


if __name__ == "__main__":
    main()
