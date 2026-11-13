"""Ready-made analyses built on pace, pit and sanity. Pure functions.

These are the standard, tested versions of what an analyst script usually
needs, so a model (or a person) does not have to re-derive them each time.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from backend.f1lab import sanity
from backend.f1lab.pace import (
    FUEL_EFFECT_S_PER_LAP,
    clean_laps,
    fit_degradation,
    fuel_correct,
    is_missing,
)
from backend.f1lab.pit import PitLoss, pit_losses, summarize_green

# Within this gap the car behind loses lap time. From a simulation of aerodynamic interaction
# (Fieni et al., arXiv 2602.23056, Bahrain), used here as an approximation for every circuit.
TRAFFIC_GAP_S = 1.35

_COLORS = ("#3d7f8a", "#d9822b", "#7a5aa6", "#4c9a6a", "#c4574c")


@dataclass(frozen=True)
class StintDeg:
    stint: int
    compound: str | None
    laps: int  # clean laps used in the fit
    first_lap: int
    last_lap: int
    raw_slope_s_per_lap: float  # no fuel correction (what a naive fit gives)
    corrected_slope_s_per_lap: float  # after fuel correction: the tyre degradation
    r2: float  # of the corrected fit; low means treat the slope as indicative
    issues: tuple[str, ...]  # codes from sanity.check_degradation


def _stints(laps: list[dict]) -> list[int]:
    return sorted({lap["stint"] for lap in laps if lap.get("stint") is not None})


def degradation_by_stint(
    laps: list[dict],
    total_laps: int,
    *,
    effect_s_per_lap: float = FUEL_EFFECT_S_PER_LAP,
    min_laps: int = 5,
) -> list[StintDeg]:
    """Cleaned, fuel-corrected degradation for each stint of ONE driver."""
    results: list[StintDeg] = []
    for stint in _stints(laps):
        stint_laps = [lap for lap in laps if lap.get("stint") == stint]
        clean = clean_laps(stint_laps)
        corrected = fuel_correct(clean, total_laps, effect_s_per_lap=effect_s_per_lap)
        raw_fit = fit_degradation(clean, min_laps=min_laps)
        fit = fit_degradation(corrected, min_laps=min_laps)
        if raw_fit is None or fit is None:
            continue
        issues = tuple(
            i.code
            for i in sanity.check_degradation(fit.slope_s_per_lap, fuel_corrected=True)
        )
        results.append(
            StintDeg(
                stint=stint,
                compound=stint_laps[0].get("compound"),
                laps=fit.laps,
                first_lap=corrected[0]["lap_number"],
                last_lap=corrected[-1]["lap_number"],
                raw_slope_s_per_lap=raw_fit.slope_s_per_lap,
                corrected_slope_s_per_lap=fit.slope_s_per_lap,
                r2=fit.r2,
                issues=issues,
            )
        )
    return results


def degradation_chart(
    laps: list[dict],
    total_laps: int,
    *,
    effect_s_per_lap: float = FUEL_EFFECT_S_PER_LAP,
    min_laps: int = 5,
) -> dict:
    """ECharts option: fuel-corrected lap times per stint with the fitted lines."""
    series: list[dict] = []
    for i, stint in enumerate(_stints(laps)):
        stint_laps = [lap for lap in laps if lap.get("stint") == stint]
        corrected = fuel_correct(
            clean_laps(stint_laps), total_laps, effect_s_per_lap=effect_s_per_lap
        )
        fit = fit_degradation(corrected, min_laps=min_laps)
        if fit is None:
            continue
        color = _COLORS[i % len(_COLORS)]
        name = (
            f"Stint {stint} {str(stint_laps[0].get('compound') or '').title()}".strip()
        )
        first, last = corrected[0]["lap_number"], corrected[-1]["lap_number"]
        series.append(
            {
                "name": name,
                "type": "scatter",
                "symbolSize": 6,
                "itemStyle": {"color": color},
                "data": [
                    [lap["lap_number"], round(lap["lap_time_ms"] / 1000, 3)]
                    for lap in corrected
                ],
            }
        )
        series.append(
            {
                "name": f"{name} fit",
                "type": "line",
                "showSymbol": False,
                "lineStyle": {"color": color, "width": 2},
                "data": [
                    [first, round(fit.intercept_s, 3)],
                    [
                        last,
                        round(
                            fit.intercept_s + fit.slope_s_per_lap * (last - first), 3
                        ),
                    ],
                ],
            }
        )
    return {
        "tooltip": {"trigger": "item"},
        "legend": {"top": 0},
        "xAxis": {"type": "value", "name": "Lap", "min": "dataMin"},
        "yAxis": {
            "type": "value",
            "name": "Fuel-corrected lap time (s)",
            "scale": True,
        },
        "series": series,
    }


def pit_summary(laps_by_driver: dict[str, list[dict]], total_laps: int) -> dict:
    """Pit stops for several drivers: every stop plus the green-flag summary.

    laps_by_driver maps a label (e.g. 'HAM') to that driver's laps.
    """
    stops: list[tuple[str, PitLoss]] = [
        (label, stop)
        for label, laps in laps_by_driver.items()
        for stop in pit_losses(laps, total_laps)
    ]
    return {
        "stops": [
            {
                "driver": label,
                "lap_in": stop.lap_in,
                "lap_out": stop.lap_out,
                "condition": stop.condition,
                "loss_s": None if stop.loss_s is None else round(stop.loss_s, 2),
                "issues": [
                    i.code for i in sanity.check_pit_loss(stop.loss_s, stop.condition)
                ],
            }
            for label, stop in stops
        ],
        "green": summarize_green([stop for _, stop in stops]),
    }


def gaps_to_car_ahead(laps: list[dict]) -> dict[tuple[int, int], float]:
    """(driver_number, lap_number) -> seconds behind the car one position ahead.

    Needs every driver's laps including deleted ones, because gaps come from summed
    lap times. After a missing lap time a driver has no gap for the rest of the race.
    """
    elapsed: dict[tuple[int, int], float] = {}
    by_driver: dict[int, list[dict]] = {}
    for lap in laps:
        by_driver.setdefault(lap["driver_number"], []).append(lap)
    for driver, rows in by_driver.items():
        total = 0.0
        for expected, lap in enumerate(sorted(rows, key=lambda r: r["lap_number"]), 1):
            if lap["lap_number"] != expected or is_missing(lap.get("lap_time_ms")):
                break
            total += lap["lap_time_ms"] / 1000
            elapsed[(driver, expected)] = total

    at_position = {
        (lap["lap_number"], lap["position"]): lap["driver_number"]
        for lap in laps
        if not is_missing(lap.get("position"))
    }
    gaps: dict[tuple[int, int], float] = {}
    for lap in laps:
        key = (lap["driver_number"], lap["lap_number"])
        if is_missing(lap.get("position")) or key not in elapsed:
            continue
        ahead = at_position.get((lap["lap_number"], lap["position"] - 1))
        ahead_time = elapsed.get((ahead, lap["lap_number"])) if ahead else None
        if ahead_time is not None:
            gaps[key] = elapsed[key] - ahead_time
    return gaps


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def race_summary(
    laps: list[dict], labels: dict[int, str], names: dict[int, str] | None = None
) -> dict:
    """Final order, stops, pace and traffic for every driver in a race.

    laps: all drivers, including deleted laps. labels: driver_number -> 'HAM'.
    names: driver_number -> full name, so a model need not guess who a code means.
    The order comes from lap data at each driver's last lap, not official results.
    """
    gaps = gaps_to_car_ahead(laps)
    race_laps = max((lap["lap_number"] for lap in laps), default=0)
    rows = []
    for driver in sorted({lap["driver_number"] for lap in laps}):
        own = sorted(
            (lap for lap in laps if lap["driver_number"] == driver),
            key=lambda r: r["lap_number"],
        )
        position_on = {lap["lap_number"]: lap.get("position") for lap in own}
        clean = clean_laps(own)
        stops = [
            {
                "lap_in": stop.lap_in,
                "condition": stop.condition,
                "loss_s": None if stop.loss_s is None else round(stop.loss_s, 2),
                "position_before": position_on.get(stop.lap_in - 1),
            }
            for stop in pit_losses(own, race_laps)
        ]
        known = [
            gaps[(driver, lap["lap_number"])]
            for lap in clean
            if (driver, lap["lap_number"]) in gaps
        ]
        compounds: list[str] = []
        for lap in own:
            compound = lap.get("compound")
            if compound and (not compounds or compounds[-1] != compound):
                compounds.append(compound)
        rows.append(
            {
                "driver": labels.get(driver, str(driver)),
                "name": (names or {}).get(driver),
                "final_position": own[-1].get("position"),
                "laps": own[-1]["lap_number"],
                "compounds": compounds,
                "stops": stops,
                "median_clean_lap_s": round(
                    median(lap["lap_time_ms"] for lap in clean) / 1000, 3
                )
                if clean
                else None,
                "final_gap_ahead_s": _rounded(
                    gaps.get((driver, own[-1]["lap_number"]))
                ),
                "clean_laps_with_gap": len(known),
                "clean_laps_in_traffic": sum(g < TRAFFIC_GAP_S for g in known),
            }
        )
    rows.sort(key=lambda r: (-r["laps"], r["final_position"] or 99))
    return {"race_laps": race_laps, "drivers": rows}


def format_race_summary(summary: dict) -> str:
    """One compact line per driver, for the model to read first."""
    lines = [
        f"Race of {summary['race_laps']} laps. Order is from lap data at each driver's last "
        f"lap, not official results. 'traffic' = clean laps within {TRAFFIC_GAP_S} s of the "
        "car ahead (an approximate threshold), out of laps where the gap is known; a stop under red, SC or VSC is not a normal racing stop. Lap times already include pit loss."
    ]
    for row in summary["drivers"]:
        stops = (
            ", ".join(
                f"L{s['lap_in']} {s['condition']}"
                + (f" {s['loss_s']}s" if s["loss_s"] is not None else "")
                + f" from P{s['position_before']}"
                for s in row["stops"]
            )
            or "none"
        )
        name = f" ({row['name']})" if row.get("name") else ""
        if row["final_position"] == 1:
            gap = ""
        elif row["final_gap_ahead_s"] is None:
            gap = "gap ahead unknown "
        else:
            gap = f"gap ahead {row['final_gap_ahead_s']}s "
        # gaps vanish after a missing lap time: say unknown rather than imply clean air
        traffic = (
            f"{row['clean_laps_in_traffic']}/{row['clean_laps_with_gap']}"
            if row["clean_laps_with_gap"]
            else "unknown"
        )
        lines.append(
            f"P{row['final_position']} {row['driver']}{name} {row['laps']}L {gap}"
            f"{'>'.join(c[0] for c in row['compounds'])} "
            f"median {row['median_clean_lap_s']}s "
            f"traffic {traffic} stops: {stops}"
        )
    return "\n".join(lines)
