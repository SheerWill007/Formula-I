"""
Deterministic strategy helpers (Task 6).

These functions contain NO database access and NO LLM calls: they turn raw
stored evidence (lap times, race-control flags, stint fits) into a bounded,
named scenario comparison. Keeping them pure makes them unit-testable and keeps
the "LLM plans, tools compute, LLM explains" contract intact -- the LLM may
describe a scenario but may never invent a pit loss or a probability.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.agent import types

_CONDITION_ORDER = ("green", "vsc", "sc", "yellow", "red")


def classify_pit_condition(flags: Iterable[str | None]) -> str:
    """Map the race-control flags in effect on a lap to one pit-loss condition.

    Safety car outranks VSC outranks red outranks yellow; a lap with no flags is
    a green-flag lap.
    """
    normalized = {f.strip().upper() for f in flags if f and f.strip()}
    if normalized & {"SC", "SAFETY CAR"}:
        return "sc"
    if normalized & {"VSC", "VIRTUAL SAFETY CAR"}:
        return "vsc"
    if "RED" in normalized:
        return "red"
    if "YELLOW" in normalized:
        return "yellow"
    return "green"


def pit_loss_ms(
    lap_in_time_ms: float | None,
    lap_out_time_ms: float | None,
    clean_lap_ms: float | None,
) -> int | None:
    """Time lost on the in/out laps versus two clean laps on the same track.

    Returns None when any input is missing -- we never fabricate a pit loss.
    """
    if lap_in_time_ms is None or lap_out_time_ms is None or clean_lap_ms is None:
        return None
    return int(round(lap_in_time_ms + lap_out_time_ms - 2 * clean_lap_ms))


def summarize_pit_losses(
    records: Iterable[tuple[str, int | None]],
) -> tuple[types.PitLossEstimate, ...]:
    """Group (condition, loss_ms) samples into per-condition estimates."""
    by_condition: dict[str, list[int]] = {}
    for condition, loss in records:
        if loss is None:
            continue
        by_condition.setdefault(condition, []).append(loss)

    estimates: list[types.PitLossEstimate] = []
    for condition in _CONDITION_ORDER:
        values = by_condition.get(condition)
        if not values:
            continue
        estimates.append(
            types.PitLossEstimate(
                condition=condition,
                sample_count=len(values),
                mean_pit_loss_ms=int(round(sum(values) / len(values))),
                min_pit_loss_ms=min(values),
                max_pit_loss_ms=max(values),
            )
        )
    return tuple(estimates)


def build_scenarios(
    *,
    current_lap: int | None,
    total_laps: int | None,
    remaining_laps: int | None,
    compound: str | None,
    degradation_slope_ms_per_lap: float | None,
    pit_loss_green_ms: int | None,
    pit_loss_vsc_ms: int | None,
    pit_loss_sc_ms: int | None,
    rain_in_session: bool,
    safety_car_periods: int,
) -> tuple[list[types.StrategyScenario], list[str], list[str]]:
    """Produce the bounded named scenario set plus assumptions and notes.

    All projected deltas are relative to staying out (the baseline, 0 ms); a
    negative delta means the scenario saves time versus staying out. Every
    unavailable input stays None and is surfaced as an assumption instead of a
    guessed number.
    """
    assumptions: list[str] = []
    notes: list[str] = []

    if remaining_laps is None:
        deg_over_remaining = None
        assumptions.append(
            "remaining race distance is unknown, so long-run degradation cost "
            "could not be projected"
        )
    elif degradation_slope_ms_per_lap is None:
        deg_over_remaining = None
        assumptions.append(
            "no usable degradation slope for the current stint; degradation "
            "cost was not projected"
        )
    else:
        deg_over_remaining = int(round(degradation_slope_ms_per_lap * remaining_laps))
        assumptions.append(
            f"degradation slope {degradation_slope_ms_per_lap:.0f} ms/lap applied "
            f"over {remaining_laps} laps"
        )

    if current_lap is None:
        assumptions.append("current lap was not provided; using the driver's last lap")
    if total_laps is not None:
        assumptions.append(f"race distance estimated from stored laps: {total_laps}")

    def _delta(pit_loss: int | None) -> int | None:
        if pit_loss is None or deg_over_remaining is None:
            return None
        return pit_loss - deg_over_remaining

    stay_out = types.StrategyScenario(
        name="stay_out",
        label="Stay out (baseline)",
        projected_delta_ms=0,
        assumptions=("baseline: no additional pit stop",),
        risks=tuple(
            r
            for r in (
                f"accumulates ~{deg_over_remaining} ms of degradation if the slope holds"
                if deg_over_remaining is not None
                else None,
                "exposed to a tyre cliff before the end of the stint",
            )
            if r
        ),
    )

    pit_now_green = types.StrategyScenario(
        name="pit_now_green",
        label="Pit now under green",
        projected_delta_ms=_delta(pit_loss_green_ms),
        assumptions=(
            f"green-flag pit loss {pit_loss_green_ms} ms"
            if pit_loss_green_ms is not None
            else "green-flag pit loss unavailable",
        ),
        risks=(
            "loses track position and may rejoin in traffic",
            "undercut exposure to cars behind",
        ),
    )

    pit_now_vsc = types.StrategyScenario(
        name="pit_now_vsc",
        label="Pit now under VSC",
        projected_delta_ms=_delta(pit_loss_vsc_ms),
        assumptions=(
            f"VSC pit loss {pit_loss_vsc_ms} ms"
            if pit_loss_vsc_ms is not None
            else "VSC pit loss unavailable; scenario cannot be costed",
        ),
        risks=("requires a VSC to be triggered while the car is near the pit entry",),
    )

    pit_now_sc = types.StrategyScenario(
        name="pit_now_sc",
        label="Pit now under safety car",
        projected_delta_ms=_delta(pit_loss_sc_ms),
        assumptions=(
            f"safety-car pit loss {pit_loss_sc_ms} ms"
            if pit_loss_sc_ms is not None
            else "safety-car pit loss unavailable; scenario cannot be costed",
        ),
        risks=("requires a safety car; field bunches up and gaps reset",),
    )

    if degradation_slope_ms_per_lap is None:
        extend_delta = None
    else:
        horizon = 5
        deg_horizon = int(round(degradation_slope_ms_per_lap * horizon))
        extend_delta = (
            deg_horizon + (pit_loss_green_ms or 0) - deg_over_remaining
            if pit_loss_green_ms is not None and deg_over_remaining is not None
            else None
        )
    extend_stint = types.StrategyScenario(
        name="extend_stint",
        label="Extend the stint (pit in ~5 laps)",
        projected_delta_ms=extend_delta,
        assumptions=("green-flag pit loss on a stop 5 laps from now",),
        risks=("longer exposure to degradation and a possible cliff",),
    )

    scenarios = [stay_out, pit_now_green, pit_now_vsc, pit_now_sc, extend_stint]

    if pit_loss_vsc_ms is None or pit_loss_sc_ms is None:
        notes.append(
            "VSC/safety-car pit losses are not fully observed in this session; "
            "those scenarios are shown but not costed."
        )
    if rain_in_session:
        notes.append(
            "this session contained rainfall; a wet/dry crossover pit could "
            "dominate the dry-tyre comparison."
        )
    if safety_car_periods > 0:
        notes.append(
            f"{safety_car_periods} safety-car/VSC period(s) observed in this session."
        )
    else:
        notes.append("no safety-car/VSC periods observed in this session.")

    return scenarios, assumptions, notes
