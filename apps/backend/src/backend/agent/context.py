"""Continuous Conversaton Context

Every run records the routing context the LLM router extracted (intent + entities, or any slot that was missing)"""

from __future__ import annotations
from typing import Any, Sequence
from backend.agent import types

_ENTITY_KEYS = (
    "driver_name",
    "compare_driver_name",
    "gp_name",
    "year",
    "target_lap",
    "session_type",
)


def routed_to_context(
    routed: types.RoutedQuestion, missing: Sequence[str] = ()
) -> dict[str, Any]:
    """Serialize the routed question into a JSON persisted on agent_runs.
    'missing' lists the slot that were still empty; which is the reason the orchestrator asked a counter question
    It drives the merge next turn"""

    return {
        "intent": routed.intent.value,
        "driver_name": routed.driver_name,
        "compare_driver_name": routed.compare_driver_name,
        "gp_name": routed.gp_name,
        "year": routed.year,
        "laps_window": routed.laps_window,
        "target_lap": routed.target_lap,
        "session_type": routed.session_type.value if routed.session_type else None,
        "missing": list(missing),
    }


def merge_context(
    prev: dict[str, Any] | None, current: types.RoutedQuestion
) -> types.RoutedQuestion:
    """Merge the previous turn context with this turn's fresh extraction."""

    if prev is None:
        return current

    missing = set(prev.get("missing") or [])
    is_resolution = len(missing) > 0
    merged: dict[str, Any] = {key: prev.get(key) for key in _ENTITY_KEYS}

    if is_resolution:
        if "driver" in missing and current.driver_name:
            merged["driver_name"] = current.driver_name

        if "compare_driver" in missing:
            merged["compare_driver_name"] = (
                current.compare_driver_name
                or current.driver_name
                or merged.get("compare_driver_name")
            )

        if "target_lap" in missing and current.target_lap is not None:
            merged["target_lap"] = current.target_lap

        if "race" in missing:
            merged["gp_name"] = current.gp_name or merged.get("gp_name")
            merged["year"] = (
                current.year if current.year is not None else merged.get("year")
            )

    else:
        if current.driver_name:
            merged["driver_name"] = current.driver_name
        if current.compare_driver_name:
            merged["compare_driver_name"] = current.compare_driver_name
        if current.gp_name:
            merged["gp_name"] = current.gp_name
        if current.year is not None:
            merged["year"] = current.year
        if current.target_lap is not None:
            merged["target_lap"] = current.target_lap

    laps_window = prev.get("laps_window", 3) if is_resolution else current.laps_window

    intent = (
        types.Intent(prev["intent"])
        if is_resolution and prev.get("intent")
        else current.intent
    )

    return types.RoutedQuestion(
        intent=intent,
        driver_name=merged.get("driver_name"),
        compare_driver_name=merged.get("compare_driver_name"),
        gp_name=merged.get("gp_name"),
        year=merged.get("year"),
        laps_window=laps_window,
        target_lap=merged.get("target_lap"),
        session_type=(
            types.SessionType(merged["session_type"])
            if merged.get("session_type")
            else None
        ),
    )
