"""Pit-stop loss measured from a driver's own laps. Pure functions: no DB, no LLM."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, median

from backend.f1lab.pace import (
    FUEL_EFFECT_S_PER_LAP,
    clean_laps,
    fuel_correct,
    is_missing,
)

# worst condition wins when the in-lap and out-lap differ
_SEVERITY = {"green": 0, "vsc": 1, "sc": 2, "red": 3}


def lap_condition(track_status: object) -> str:
    """'green' | 'vsc' | 'sc' | 'red' from a lap's track_status string."""
    codes = set(str(track_status or ""))
    if "5" in codes:
        return "red"
    if "4" in codes:
        return "sc"
    if codes & {"6", "7"}:
        return "vsc"
    return "green"


@dataclass(frozen=True)
class PitLoss:
    lap_in: int
    lap_out: int
    condition: str
    loss_s: float | None  # None when it cannot be measured from own laps
    ref_laps: int  # clean laps around the stop used as the pace reference


def pit_losses(
    laps: list[dict],
    total_laps: int,
    *,
    ref_window: int = 3,
    effect_s_per_lap: float = FUEL_EFFECT_S_PER_LAP,
) -> list[PitLoss]:
    """One PitLoss per stop of ONE driver.

    loss = (in-lap + out-lap) - 2 x reference pace, all fuel-corrected. The
    reference is the mean of up to `ref_window` clean laps before the in-lap
    and after the out-lap (so tyre age roughly cancels). Only green stops get
    a number: under SC/VSC/red the own-lap method is meaningless, so loss_s
    is None there. A stop with a missing lap time is still listed, without a loss.
    """
    by_lap = {lap["lap_number"]: lap for lap in laps}
    clean = fuel_correct(
        clean_laps(laps), total_laps, effect_s_per_lap=effect_s_per_lap
    )

    stops: list[PitLoss] = []
    for lap in sorted(laps, key=lambda lap: lap["lap_number"]):
        if is_missing(lap.get("pit_in_time_ms")):
            continue
        n = lap["lap_number"]
        nxt = by_lap.get(n + 1)
        if nxt is None or is_missing(nxt.get("pit_out_time_ms")):
            continue  # came in and never rejoined: a retirement, not a stop

        condition = max(
            lap_condition(lap.get("track_status")),
            lap_condition(nxt.get("track_status")),
            key=_SEVERITY.__getitem__,
        )
        before = [c for c in clean if c["lap_number"] < n][-ref_window:]
        after = [c for c in clean if c["lap_number"] > n + 1][:ref_window]
        refs = before + after

        loss_s = None
        times_known = not (
            is_missing(lap.get("lap_time_ms")) or is_missing(nxt.get("lap_time_ms"))
        )
        if condition == "green" and len(refs) >= 2 and times_known:
            in_c, out_c = fuel_correct(
                [lap, nxt], total_laps, effect_s_per_lap=effect_s_per_lap
            )
            ref_ms = fmean(c["lap_time_ms"] for c in refs)
            loss_s = (in_c["lap_time_ms"] + out_c["lap_time_ms"] - 2 * ref_ms) / 1000
        stops.append(PitLoss(n, n + 1, condition, loss_s, len(refs)))
    return stops


def summarize_green(losses: list[PitLoss]) -> dict | None:
    """Median/min/max over measured green stops, or None if there are none."""
    values = [
        p.loss_s for p in losses if p.condition == "green" and p.loss_s is not None
    ]
    if not values:
        return None
    return {
        "n": len(values),
        "median_s": median(values),
        "min_s": min(values),
        "max_s": max(values),
    }
