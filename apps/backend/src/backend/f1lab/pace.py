"""Lap-time cleaning, fuel correction and tyre degradation.

Pure functions: no DB, no LLM. Laps are dicts shaped like lap_times rows.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from statistics import fmean, median

# Track-status codes that mean SC / VSC / red flag. Laps carrying any of them
SLOW_TRACK_STATUS = frozenset({"4", "5", "6", "7"})

# ASSUMPTION, not measured: seconds a lap costs per remaining lap of fuel.
# Calibrate per circuit later; every answer that uses it must say so.
FUEL_EFFECT_S_PER_LAP = 0.05


def is_missing(value: object) -> bool:
    """None or NaN. Laps coming from pandas carry NaN where the database has NULL."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def clean_laps(laps: list[dict], *, outlier_pct: float = 0.07) -> list[dict]:
    """Keep only representative racing laps, sorted by lap number."""
    usable: list[dict] = []
    for lap in laps:
        if is_missing(lap.get("lap_time_ms")) or lap["lap_number"] == 1:
            continue
        if not is_missing(lap.get("pit_in_time_ms")) or not is_missing(
            lap.get("pit_out_time_ms")
        ):
            continue
        if lap.get("deleted"):
            continue
        if set(str(lap.get("track_status") or "")) & SLOW_TRACK_STATUS:
            continue
        usable.append(lap)

    by_stint: dict[object, list[dict]] = {}
    for lap in usable:
        by_stint.setdefault(lap.get("stint"), []).append(lap)

    kept: list[dict] = []
    for stint_laps in by_stint.values():
        limit = median(lap["lap_time_ms"] for lap in stint_laps) * (1 + outlier_pct)
        kept += [lap for lap in stint_laps if lap["lap_time_ms"] <= limit]
    return sorted(kept, key=lambda lap: lap["lap_number"])


def fuel_correct(
    laps: list[dict],
    total_laps: int,
    *,
    effect_s_per_lap: float = FUEL_EFFECT_S_PER_LAP,
) -> list[dict]:
    """Copies of `laps` with lap_time_ms adjusted to an empty-tank car.

    Lap n still carries (total_laps - n) laps of fuel, each costing
    effect_s_per_lap, so that cost is subtracted. Inputs are not mutated.
    """
    corrected = []
    for lap in laps:
        remaining = max(total_laps - lap["lap_number"], 0)
        adjusted = lap["lap_time_ms"] - remaining * effect_s_per_lap * 1000
        corrected.append({**lap, "lap_time_ms": adjusted})
    return corrected


@dataclass(frozen=True)
class DegFit:
    laps: int
    slope_s_per_lap: float
    intercept_s: float
    r2: float


def fit_degradation(laps: list[dict], *, min_laps: int = 5) -> DegFit | None:
    """Least-squares lap time vs tyre age for ONE stint. None if too few laps."""

    if len(laps) < min_laps:
        return None
    first = laps[0]["lap_number"]

    xs = [float(lap["lap_number"] - first) for lap in laps]
    ys = [lap["lap_time_ms"] / 1000 for lap in laps]
    x_mean, y_mean = fmean(xs), fmean(ys)

    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx == 0:
        return None

    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / sxx
    intercept = y_mean - slope * x_mean

    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0

    return DegFit(len(laps), slope, intercept, r2)
